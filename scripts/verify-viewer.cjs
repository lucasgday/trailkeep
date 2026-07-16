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
    const resolved = require.resolve("playwright");
    const { chromium } = require(resolved);
    if (fs.existsSync(chromium.executablePath())) return resolved;
  } catch (_) {
    // Continue to explicit candidates.
  }
  const candidates = candidatePlaywrightPaths()
    .filter((candidate) => fs.existsSync(path.join(candidate, "package.json")))
    .filter((candidate) => {
      try {
        const { chromium } = require(candidate);
        return fs.existsSync(chromium.executablePath());
      } catch (_) {
        return false;
      }
    })
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
  const requestedFixture = process.env.TRAILKEEP_VIEWER_FIXTURE_DIR;
  const fixture = requestedFixture
    ? path.resolve(requestedFixture)
    : fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-viewer-fixture-"));
  if (requestedFixture) {
    if (fs.existsSync(fixture)) throw new Error(`TRAILKEEP_VIEWER_FIXTURE_DIR already exists: ${fixture}`);
    fs.mkdirSync(fixture, { recursive: true });
  }
  try {
    const sessions = path.join(fixture, "markdown-claude", "fixture-project");
    const codexSessions = path.join(fixture, "markdown-codex", "fixture-project");
    fs.mkdirSync(sessions, { recursive: true });
    fs.mkdirSync(codexSessions, { recursive: true });
    fs.writeFileSync(path.join(fixture, "README.md"), "# Repository notes should not load\n\n### You\n\nNot a conversation.\n");
    fs.writeFileSync(path.join(sessions, "invalid.md"), "# Invalid metadata should not load\n\n### You\n\nNot a trailkeep session.\n");
    fs.writeFileSync(path.join(sessions, "valid.md"), "# Valid fixture conversation\n\n<!-- date: 2026-07-10T10:00:00Z | id: fixture-session | project: fixture-project | source: claude-code | archived: false -->\n\n### You\n\nKeep this one.\n\n### Claude\n\nLoaded.\n");
    fs.writeFileSync(path.join(codexSessions, "parent.md"), "# Parent fixture conversation\n\n<!-- date: 2026-07-11T10:00:00Z | id: fixture-codex-parent | project: fixture-project | source: codex | archived: false | format_version: 2 -->\n\n### You\n\nAudit the detail contract.\n\n### Codex\n\nI will delegate the detail and test audits.\n\n[tool: spawn_agent → detail_audit]\n\n[result]\n\nStarted detail audit.\n");
    fs.writeFileSync(path.join(codexSessions, "detail.md"), "# Detail audit\n\n<!-- date: 2026-07-11T10:01:00Z | id: fixture-codex-detail | project: fixture-project | source: codex | archived: false | format_version: 2 | parent_id: fixture-codex-parent | agent_path: detail_audit | agent_nickname: Detail analyst | agent_depth: 1 | agent_status: completed | completed_at: 2026-07-11T10:03:00Z -->\n\n### Codex\n\nDetail-only evidence is preserved.\n\n[tool: spawn_agent → nested_check]\n\n[result]\n\nStarted nested check.\n");
    fs.writeFileSync(path.join(codexSessions, "nested.md"), "# Nested check\n\n<!-- date: 2026-07-11T10:02:00Z | id: fixture-codex-nested | project: fixture-project | source: codex | archived: false | format_version: 2 | parent_id: fixture-codex-detail | agent_path: detail_audit/nested_check | agent_nickname: Nested verifier | agent_depth: 2 | agent_status: completed | completed_at: 2026-07-11T10:02:30Z -->\n\n### Codex\n\nNested-only evidence is visible and searchable.\n");
    fs.writeFileSync(path.join(codexSessions, "test-scope.md"), "# Test scope\n\n<!-- parent_id: fixture-codex-parent | date: 2026-07-11T10:01:30Z | id: fixture-codex-tests | project: fixture-project | source: codex | archived: false | format_version: 2 | agent_path: test_scope | agent_nickname: Test analyst | agent_depth: 1 | agent_status: in_progress -->\n\n### Codex\n\nTest-scope evidence remains available.\n");
    fs.writeFileSync(path.join(codexSessions, "orphan.md"), "# Orphan fixture subagent\n\n<!-- date: 2026-07-11T10:04:00Z | id: fixture-codex-orphan | project: fixture-project | source: codex | archived: false | format_version: 2 | parent_id: missing-parent | agent_path: orphan_audit | agent_nickname: Orphan analyst | agent_depth: 1 | agent_status: completed -->\n\n### Codex\n\nThe missing parent must not hide this session.\n");
    await page.locator("#folder").setInputFiles(fixture);
    await page.waitForFunction(() => document.querySelectorAll(".proj-card").length === 1);
    const loaded = await page.locator("body").innerText();
    if (!loaded.includes("fixture-project")) run.failures.push("valid markdown-* conversation did not load");
    if (loaded.includes("Repository notes should not load")) run.failures.push("root README was loaded as a conversation");
    if (loaded.includes("Invalid metadata should not load")) run.failures.push("invalid markdown metadata was loaded as a conversation");
    run.fixtureProjects = await page.locator(".proj-card").count();

    await page.locator(".proj-card").click();
    await page.waitForFunction(() => document.querySelectorAll(".ph-conv-main").length === 3);
    const projectRows = await page.locator(".ph-conv-main").allTextContents();
    if (projectRows.some((row) => /Detail audit|Nested check|Test scope/.test(row))) {
      run.failures.push("linked subagents were rendered as root project conversations");
    }
    const orphanRow = page.locator(".ph-conv", { hasText: "Orphan fixture subagent" });
    if (!await orphanRow.locator(".subagent-orphan").count()) run.failures.push("orphan subagent is missing its parent-warning badge");

    await page.locator(".ph-conv-main", { hasText: "Parent fixture conversation" }).click();
    await page.waitForFunction(() => document.querySelectorAll(".subagent-node").length === 2);
    const detail = page.locator('.subagent-node[data-subagent-id$="/detail.md"]');
    const tests = page.locator('.subagent-node[data-subagent-id$="/test-scope.md"]');
    if (!await page.locator('[data-session$="/parent.md"][data-type="tool"] + .subagent-node[data-subagent-id$="/detail.md"]').count()) {
      run.failures.push("detail subagent was not anchored immediately after its spawn tool");
    }
    if (!await tests.locator(".subagent-status.in-progress").count()) run.failures.push("in-progress snapshot status did not render");
    if (!await detail.locator(".subagent-status.completed").count()) run.failures.push("completed snapshot status did not render");
    if (!await page.locator(".subagent-fallback", { has: tests }).count()) run.failures.push("unanchored subagent fallback did not render");
    if (await page.locator('.subagent-node[data-subagent-id$="/nested.md"]').count()) run.failures.push("nested subagent rendered before its parent was expanded");

    const detailToggle = detail.locator(":scope > .subagent-toggle");
    await detailToggle.focus();
    await detailToggle.press("Enter");
    const detailExpanded = await detailToggle.getAttribute("aria-expanded");
    if (detailExpanded !== "true") run.failures.push("keyboard activation did not expand the subagent");
    await page.waitForTimeout(100);
    const renderedSubagentIds = await page.locator(".subagent-node").evaluateAll((nodes) => nodes.map((node) => node.dataset.subagentId));
    if (!await page.locator('.subagent-node[data-subagent-id$="/nested.md"]').count()) {
      throw new Error(`nested subagent did not render after expansion: expanded=${detailExpanded}, ids=${renderedSubagentIds.join(",")}`);
    }
    if (!await detail.getByText("Detail-only evidence is preserved.").count()) run.failures.push("expanded child content did not render");

    const nested = page.locator('.subagent-node[data-subagent-id$="/nested.md"]');
    const nestedToggle = nested.locator(":scope > .subagent-toggle");
    await nestedToggle.press("Enter");
    if (!await nested.getByText("Nested-only evidence is visible and searchable.").count()) run.failures.push("nested child content did not render");

    await nestedToggle.press("Enter");
    await detailToggle.press("Enter");
    await page.locator("#search").fill("nested-only evidence");
    await page.waitForTimeout(200);
    const parentSearchResult = page.locator(".sess-body", { hasText: "Parent fixture conversation" });
    if (!await parentSearchResult.count()) run.failures.push("descendant-only search did not retain its parent result");
    else await parentSearchResult.click();
    if (await page.locator('.subagent-node[data-subagent-id$="/detail.md"] > .subagent-toggle').getAttribute("aria-expanded") !== "true"
      || await page.locator('.subagent-node[data-subagent-id$="/nested.md"] > .subagent-toggle').getAttribute("aria-expanded") !== "true") {
      run.failures.push("descendant search did not expand the matching ancestor path");
    }

    const screenshotPath = process.env.TRAILKEEP_VIEWER_SCREENSHOT;
    if (screenshotPath) {
      const absoluteScreenshot = path.resolve(screenshotPath);
      fs.mkdirSync(path.dirname(absoluteScreenshot), { recursive: true });
      await page.locator("#reader").screenshot({ path: absoluteScreenshot });
      run.screenshot = absoluteScreenshot;
    }

    await page.locator("#search").fill("");
    await page.waitForTimeout(200);
    await page.locator('.cb-count[data-type="tool"]').click();
    if (!await page.locator('.subagent-node[data-subagent-id$="/detail.md"]').count()) run.failures.push("tool filtering hid the subagent disclosure");

    await page.setViewportSize({ width: 390, height: 844 });
    const mobileLayout = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      page: document.documentElement.scrollWidth,
      targets: [...document.querySelectorAll(".subagent-toggle")].every((node) => node.getBoundingClientRect().height >= 44),
    }));
    if (mobileLayout.page > mobileLayout.viewport) run.failures.push(`mobile layout overflows horizontally (${mobileLayout.page} > ${mobileLayout.viewport})`);
    if (!mobileLayout.targets) run.failures.push("subagent disclosure touch target is below 44px on mobile");

    run.subagentHierarchy = {
      rootConversations: projectRows.length,
      linkedSubagents: 3,
      orphanVisible: !!await orphanRow.count(),
      mobileLayout,
    };
    if (requestedFixture) run.fixturePath = fixture;
  } finally {
    if (!requestedFixture) fs.rmSync(fixture, { recursive: true, force: true });
  }
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

  await page.goto(`file://${file}?view=subagents&lang=es`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__DEMO_READY);
  const demoChild = page.locator('.subagent-node[data-subagent-id$="demo-agent-child.md"]');
  if (await demoChild.count() !== 1) run.failures.push("subagent demo did not open the parent conversation");
  if (await page.locator('.subagent-node[data-subagent-id$="demo-agent-grandchild.md"]').count()) {
    run.failures.push("demo grandchild rendered before its parent was expanded");
  }
  if (await demoChild.count()) {
    if (!await demoChild.locator(".subagent-status.completed").count()) run.failures.push("demo child status did not render");
    await demoChild.locator(":scope > .subagent-toggle").click();
    const demoGrandchild = page.locator('.subagent-node[data-subagent-id$="demo-agent-grandchild.md"]');
    await demoGrandchild.waitFor({ state: "attached" });
    if (!await demoGrandchild.locator(".subagent-status.in-progress").count()) run.failures.push("demo grandchild status did not render");
    const demoSpanish = await demoGrandchild.innerText();
    if (!/Subagente/i.test(demoSpanish) || !/en curso al respaldar/i.test(demoSpanish)) run.failures.push("Spanish subagent labels are incomplete");
  }
  run.subagentDemo = {
    rootCountPreserved: (await page.locator("#globalCount .gc-total").innerText()).trim() === "79",
    childRendered: await demoChild.count() === 1,
  };
  if (!run.subagentDemo.rootCountPreserved) run.failures.push("demo root conversation count included linked subagents");

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
    console.error(err && err.stack ? err.stack : err);
    process.exitCode = 1;
  });
