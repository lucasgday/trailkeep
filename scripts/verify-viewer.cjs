#!/usr/bin/env node
/*
 * Optional QA check for trailkeep's standalone viewer.
 *
 * This script is deliberately not part of update-backup.sh. It is a dev/QA
 * helper that uses Playwright when available, opens viewer.html and docs/index.html
 * through file://, blocks any http(s) request, and fails on console errors.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

function usage() {
  console.log(`Usage: node scripts/verify-viewer.cjs [--headed]

Optional Playwright QA for viewer.html and docs/index.html.

Prerequisite:
  npx playwright install chromium

If Playwright is not resolvable, install/cache it for QA with:
  npx --package playwright node scripts/verify-viewer.cjs

This script is not used by update-backup.sh.`);
}

function parseArgs(argv) {
  const options = { headed: false, help: false };
  for (const arg of argv) {
    if (arg === "--headed") options.headed = true;
    else if (arg === "-h" || arg === "--help") options.help = true;
    else throw new Error(`Unknown option: ${arg}`);
  }
  return options;
}

function candidatePlaywrightPaths() {
  const candidates = [];
  if (process.env.PLAYWRIGHT_PACKAGE_DIR) candidates.push(process.env.PLAYWRIGHT_PACKAGE_DIR);
  candidates.push(path.join(ROOT, "node_modules", "playwright"));

  const npxRoot = path.join(os.homedir(), ".npm", "_npx");
  try {
    for (const name of fs.readdirSync(npxRoot)) {
      const candidate = path.join(npxRoot, name, "node_modules", "playwright");
      candidates.push(candidate);
    }
  } catch (_) {
    // npx cache is optional.
  }

  return [...new Set(candidates)];
}

function resolvePlaywright() {
  try {
    return require.resolve("playwright");
  } catch (_) {
    // Continue to explicit candidates.
  }
  const candidates = candidatePlaywrightPaths()
    .filter((candidate) => fs.existsSync(path.join(candidate, "package.json")))
    .sort((a, b) => {
      const at = fs.statSync(path.join(a, "package.json")).mtimeMs;
      const bt = fs.statSync(path.join(b, "package.json")).mtimeMs;
      return bt - at;
    });
  if (candidates[0]) return candidates[0];
  return "";
}

function assertFile(relPath) {
  const abs = path.join(ROOT, relPath);
  if (!fs.existsSync(abs)) throw new Error(`Missing ${relPath}`);
  return abs;
}

async function checkNoErrors(page, run, errors, blockedRequests) {
  if (errors.length) run.failures.push(`console/page errors: ${errors.join(" | ")}`);
  if (blockedRequests.length) run.failures.push(`network requests attempted: ${[...new Set(blockedRequests)].join(", ")}`);
  const bodyText = await page.locator("body").innerText();
  run.bodySample = bodyText.replace(/\s+/g, " ").slice(0, 180);
}

async function verifyStandalone(browser) {
  const file = assertFile("viewer.html");
  const run = { name: "viewer.html", failures: [] };
  const errors = [];
  const blockedRequests = [];
  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (/^https?:\/\//i.test(url)) {
      blockedRequests.push(url);
      return route.abort();
    }
    return route.continue();
  });
  await page.goto(`file://${file}`, { waitUntil: "load" });
  await page.waitForTimeout(250);
  const text = await page.locator("body").innerText();
  if (!/Open folder|Abrir carpeta/.test(text)) run.failures.push("missing open-folder CTA");
  await checkNoErrors(page, run, errors, blockedRequests);
  await page.close();
  return run;
}

async function verifyDemo(browser) {
  const file = assertFile(path.join("docs", "index.html"));
  const run = { name: "docs/index.html", failures: [] };
  const errors = [];
  const blockedRequests = [];
  const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));
  await page.route("**/*", (route) => {
    const url = route.request().url();
    if (/^https?:\/\//i.test(url)) {
      blockedRequests.push(url);
      return route.abort();
    }
    return route.continue();
  });
  await page.goto(`file://${file}`, { waitUntil: "load" });
  await page.waitForTimeout(250);

  const splashAccept = page.locator("#dsAccept");
  if (await splashAccept.count()) await splashAccept.click();

  const projectsButton = page.locator("#btnProjects");
  if (await projectsButton.count()) await projectsButton.click();
  await page.waitForTimeout(250);

  const projectCards = page.locator(".proj-card");
  const cardCount = await projectCards.count();
  if (!cardCount) run.failures.push("no project cards rendered");
  const repoLinks = await page.locator(".proj-card .pj-repo").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href")).filter(Boolean));
  if (!repoLinks.length) run.failures.push("no project repo links rendered");
  if (cardCount) await projectCards.first().click();
  await page.waitForTimeout(250);

  const projectHomeText = await page.locator("body").innerText();
  if (!/Project review|Review de proyecto|Actualizar este proyecto ahora|Update this project now/.test(projectHomeText)) {
    run.failures.push("project home review UI did not render");
  }

  const runsButton = page.locator("#btnLog");
  if (await runsButton.count()) await runsButton.click();
  await page.waitForTimeout(250);
  const runsText = await page.locator("body").innerText();
  if (!/Runs|Corridas|Daily project pulse/.test(runsText)) run.failures.push("runs view did not render");

  await checkNoErrors(page, run, errors, blockedRequests);
  run.repoLinks = repoLinks.slice(0, 3);
  await page.close();
  return run;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    usage();
    return 0;
  }

  const playwrightPath = resolvePlaywright();
  if (!playwrightPath) {
    usage();
    throw new Error("Playwright package not found");
  }

  const { chromium } = require(playwrightPath);
  const browser = await chromium.launch({ headless: !options.headed });
  try {
    const runs = [];
    runs.push(await verifyStandalone(browser));
    runs.push(await verifyDemo(browser));
    const failed = runs.filter((run) => run.failures.length);
    console.log(JSON.stringify({ ok: failed.length === 0, runs }, null, 2));
    return failed.length ? 1 : 0;
  } finally {
    await browser.close();
  }
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch((err) => {
    console.error(err && err.message ? err.message : err);
    process.exitCode = 1;
  });
