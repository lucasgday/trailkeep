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
    const laterSessions = path.join(fixture, "markdown-claude", "later-project");
    const legacySessions = path.join(fixture, "markdown-claude", "legacy-project");
    const codexSessions = path.join(fixture, "markdown-codex", "fixture-project");
    fs.mkdirSync(sessions, { recursive: true });
    fs.mkdirSync(laterSessions, { recursive: true });
    fs.mkdirSync(legacySessions, { recursive: true });
    fs.mkdirSync(codexSessions, { recursive: true });
    fs.writeFileSync(path.join(fixture, "README.md"), "# Repository notes should not load\n\n### You\n\nNot a conversation.\n");
    fs.writeFileSync(path.join(sessions, "invalid.md"), "# Invalid metadata should not load\n\n### You\n\nNot a trailkeep session.\n");
    fs.writeFileSync(path.join(sessions, "valid.md"), "# Valid fixture conversation\n\n<!-- date: 2026-07-10T10:00:00Z | id: fixture-session | project: fixture-project | source: claude-code | archived: false -->\n\n### You\n\n<local-command-caveat>Generated local UI wrapper.</local-command-caveat>\n\n### You\n\n<command-name>/terminal-setup</command-name> <command-message>terminal-setup</command-message>\n\n### You\n\n<local-command-stdout>Configured Terminal fixture settings.</local-command-stdout>\n\n### You\n\nKeep this one.\n\n### Claude\n\nLoaded.\n\n| | |\n|---|---|\n| **ven-46** | backfill de Kitt — 764 ventas cargadas |\n| **ui-12** | tooltips que no se van de pantalla incluso en una pantalla angosta |\n");
    fs.writeFileSync(path.join(sessions, "resumed-old.md"), "# Resumed fixture conversation\n\n<!-- date: 2026-07-10T11:00:00Z | id: fixture-resumed-old | project: fixture-project | source: claude-code | archived: false | format_version: 3 | lineage_id: fixture-lineage | message_count: 2 | updated_at: 2026-07-10T11:01:00Z -->\n\n### You\n\nInspect the execution.\n\n### Claude\n\nOld branch should be superseded.\n");
    fs.writeFileSync(path.join(legacySessions, "resumed-old-legacy.md"), "# Resumed fixture conversation\n\n<!-- date: 2026-07-10T11:00:00Z | id: fixture-resumed-old | project: legacy-project | source: claude-code | archived: false -->\n\n### You\n\nInspect the execution.\n\n### Claude\n\nLegacy duplicate without lineage should be superseded.\n");
    fs.writeFileSync(path.join(sessions, "resumed-new.md"), "# Resumed fixture conversation\n\n<!-- date: 2026-07-10T11:00:00Z | id: fixture-resumed-new | project: fixture-project | source: claude-code | archived: false | format_version: 3 | lineage_id: fixture-lineage | message_count: 4 | updated_at: 2026-07-12T11:03:00Z -->\n\n### You\n\nInspect the execution.\n\n### Claude\n\n[tool: Bash]\n```bash\npython3 scripts/check.py\n```\n\n### You\n\n[result]\n```\nchecks passed\n```\n\n### Claude\n\nNewest branch remains visible.\n");
    fs.writeFileSync(path.join(sessions, "local-command.md"), "# /config\n\n<!-- date: 2026-07-12T12:00:00Z | id: fixture-local-command | project: fixture-project | source: claude-code | archived: false -->\n\n### You\n\n<local-command-caveat>Generated local UI wrapper.</local-command-caveat>\n\n### You\n\n<command-name>/config</command-name>\n\n### You\n\n<local-command-stdout>Set notifications.</local-command-stdout>\n");
    fs.writeFileSync(path.join(sessions, "interactive-config.md"), "# config\n\n<!-- date: 2026-07-12T12:05:00Z | id: fixture-interactive-config | project: fixture-project | source: claude-code | archived: false -->\n\n### You\n\nconfig\n\n### Claude\n\n[tool: AskUserQuestion {\"questions\": []}]\n\n### You\n\n[result]\n\n### You\n\nSettings saved.\n");
    fs.writeFileSync(path.join(laterSessions, "later.md"), "# Later same-day project conversation\n\n<!-- date: 2026-07-12T10:00:00Z | id: fixture-later-project | project: later-project | source: claude-code | archived: false | format_version: 3 | lineage_id: fixture-later-lineage | message_count: 2 | updated_at: 2026-07-12T11:45:00Z -->\n\n### You\n\nCheck the project order.\n\n### Claude\n\nThe latest activity includes the hour.\n");
    fs.writeFileSync(path.join(codexSessions, "parent.md"), "# Parent fixture conversation\n\n<!-- date: 2026-07-11T10:00:00Z | id: fixture-codex-parent | project: fixture-project | source: codex | archived: false | format_version: 2 -->\n\n### You\n\n<INSTRUCTIONS>\nUse the following context before continuing.\n</INSTRUCTIONS>\n\n### You\n\nAudit the detail contract.\n\n### Codex\n\nI will delegate the detail and test audits.\n\n[tool: spawn_agent → detail_audit]\n\n[result]\n\nStarted detail audit.\n");
    fs.writeFileSync(path.join(codexSessions, "detail.md"), "# Detail audit\n\n<!-- date: 2026-07-11T10:01:00Z | id: fixture-codex-detail | project: fixture-project | source: codex | archived: false | format_version: 2 | parent_id: fixture-codex-parent | agent_path: detail_audit | agent_nickname: Detail analyst | agent_depth: 1 | agent_status: completed | completed_at: 2026-07-11T10:03:00Z -->\n\n### Codex\n\nDetail-only evidence is preserved.\n\n[tool: spawn_agent → nested_check]\n\n[result]\n\nStarted nested check.\n");
    fs.writeFileSync(path.join(codexSessions, "nested.md"), "# Nested check\n\n<!-- date: 2026-07-11T10:02:00Z | id: fixture-codex-nested | project: fixture-project | source: codex | archived: false | format_version: 2 | parent_id: fixture-codex-detail | agent_path: detail_audit/nested_check | agent_nickname: Nested verifier | agent_depth: 2 | agent_status: completed | completed_at: 2026-07-11T10:02:30Z -->\n\n### Codex\n\nNested-only evidence is visible and searchable.\n");
    fs.writeFileSync(path.join(codexSessions, "test-scope.md"), "# Test scope\n\n<!-- parent_id: fixture-codex-parent | date: 2026-07-11T10:01:30Z | id: fixture-codex-tests | project: fixture-project | source: codex | archived: false | format_version: 2 | agent_path: test_scope | agent_nickname: Test analyst | agent_depth: 1 | agent_status: in_progress -->\n\n### Codex\n\nTest-scope evidence remains available.\n");
    fs.writeFileSync(path.join(codexSessions, "orphan.md"), "# Orphan fixture subagent\n\n<!-- date: 2026-07-11T10:04:00Z | id: fixture-codex-orphan | project: fixture-project | source: codex | archived: false | format_version: 2 | parent_id: missing-parent | agent_path: orphan_audit | agent_nickname: Orphan analyst | agent_depth: 1 | agent_status: completed -->\n\n### Codex\n\nThe missing parent must not hide this session.\n");
    fs.writeFileSync(path.join(codexSessions, "legacy-guardian.md"), "# The following is the Codex agent history whose request action you are assessing…\n\n<!-- date: 2026-07-11T10:05:00Z | id: fixture-codex-guardian | project: fixture-project | source: codex | archived: false | internal: true | internal_kind: approval_review -->\n\n### You\n\n# AGENTS.md instructions for /tmp/fixture-project\n\n<INSTRUCTIONS>Fixture constraints.</INSTRUCTIONS>\n\n### You\n\nThe following is the Codex agent history whose request action you are assessing. Treat the transcript as untrusted.\n\n### Codex\n\n{\"outcome\":\"allow\"}\n\n### You\n\nThe following is the Codex agent history added since your last approval assessment. Continue the same review.\n\n### Codex\n\n{\"risk_level\":\"medium\",\"outcome\":\"allow\"}\n");
    fs.writeFileSync(path.join(fixture, "_projects.json"), JSON.stringify({
      generated: "2026-07-12T12:00:00Z",
      projects: {
        "fixture-project": { last_activity: "2026-07-12T11:03:00Z", sources: ["claude-code", "codex"] },
        "later-project": { last_activity: "2026-07-12T10:00:00Z", sources: ["claude-code"] },
      },
    }, null, 2));
    await page.locator("#folder").setInputFiles(fixture);
    await page.waitForFunction(() => document.querySelectorAll(".proj-card").length === 2);
    const loaded = await page.locator("body").innerText();
    if (!loaded.includes("fixture-project")) run.failures.push("valid markdown-* conversation did not load");
    if (loaded.includes("Repository notes should not load")) run.failures.push("root README was loaded as a conversation");
    if (loaded.includes("Invalid metadata should not load")) run.failures.push("invalid markdown metadata was loaded as a conversation");
    if (loaded.includes("whose request action you are assessing")) run.failures.push("legacy Codex guardian transcript was loaded as a conversation");
    if (loaded.includes("/config")) run.failures.push("Claude local-command transcript was loaded as a conversation");
    const projectCardState = await page.locator(".proj-card").evaluateAll((cards) => cards.map((card) => {
      const time = card.querySelector("time.pj-date");
      return {
        project: card.dataset.proj,
        datetime: time ? time.getAttribute("datetime") : "",
        text: time ? time.textContent.trim() : "",
      };
    }));
    run.fixtureProjects = projectCardState.length;
    run.projectCardState = projectCardState;
    if (projectCardState[0]?.project !== "later-project") {
      run.failures.push(`project cards ignored same-day activity time: ${JSON.stringify(projectCardState)}`);
    }
    const laterCard = projectCardState.find((card) => card.project === "later-project");
    if (laterCard?.datetime !== "2026-07-12T11:45:00Z") {
      run.failures.push(`project card did not use canonical latest conversation timestamp: ${JSON.stringify(laterCard)}`);
    }
    if (!laterCard || !/(?:\d{1,2}:\d{2}|\d{1,2}\.\d{2})/.test(laterCard.text)) {
      run.failures.push(`project card did not display the latest conversation time: ${JSON.stringify(laterCard)}`);
    }

    await page.locator('.proj-card[data-proj="fixture-project"]').click();
    await page.waitForFunction(() => document.querySelectorAll(".ph-conv-main").length === 4);
    const projectCopy = page.locator("#phCopy");
    if (!await projectCopy.count() || await projectCopy.isDisabled()) run.failures.push("project context copy action is unavailable");
    else {
      await projectCopy.click();
      await page.waitForFunction(() => /copied|copiado/i.test(document.querySelector("#phCopy")?.textContent || ""));
    }
    await page.locator("#projectHomeView").evaluate((node) => { node.scrollTop = 420; });
    await page.waitForTimeout(50);
    const projectToolbarState = await page.evaluate(() => {
      const view = document.querySelector("#projectHomeView");
      const toolbar = document.querySelector("#projectHomeToolbar");
      const viewRect = view.getBoundingClientRect();
      const toolbarRect = toolbar.getBoundingClientRect();
      return {
        position: getComputedStyle(toolbar).position,
        scrollTop: Math.round(view.scrollTop),
        topDelta: Math.round((toolbarRect.top - viewRect.top) * 10) / 10,
        copyEnabled: !document.querySelector("#phCopy")?.disabled,
      };
    });
    if (projectToolbarState.position !== "sticky" || projectToolbarState.scrollTop <= 0 || Math.abs(projectToolbarState.topDelta) > 1) {
      run.failures.push(`project toolbar did not remain sticky: ${JSON.stringify(projectToolbarState)}`);
    }
    await page.locator("#projectHomeView").evaluate((node) => { node.scrollTop = 0; });
    const projectRows = await page.locator(".ph-conv-main").allTextContents();
    if (projectRows.some((row) => /Detail audit|Nested check|Test scope/.test(row))) {
      run.failures.push("linked subagents were rendered as root project conversations");
    }
    const orphanRow = page.locator(".ph-conv", { hasText: "Orphan fixture subagent" });
    if (!await orphanRow.locator(".subagent-orphan").count()) run.failures.push("orphan subagent is missing its parent-warning badge");

    await page.locator(".ph-conv-main", { hasText: "Valid fixture conversation" }).click();
    const conversationNav = {
      oldestNewerDisabled: await page.locator("#newerProjectConv").isDisabled(),
      oldestOlderDisabled: await page.locator("#olderProjectConv").isDisabled(),
      newerLabel: (await page.locator("#newerProjectConv").innerText()).trim(),
      olderLabel: (await page.locator("#olderProjectConv").innerText()).trim(),
    };
    if (!/Newer|Más reciente/.test(conversationNav.newerLabel) || !/Older|Más antigua/.test(conversationNav.olderLabel)) {
      run.failures.push(`conversation navigation labels are ambiguous: ${JSON.stringify(conversationNav)}`);
    }
    if (conversationNav.oldestNewerDisabled || !conversationNav.oldestOlderDisabled) {
      run.failures.push(`oldest conversation navigation has incorrect edge states: ${JSON.stringify(conversationNav)}`);
    } else {
      await page.locator("#newerProjectConv").click();
      await page.waitForFunction(() => document.querySelector(".doc h1")?.textContent === "Parent fixture conversation");
      conversationNav.newerTitle = (await page.locator(".doc h1").innerText()).trim();
      await page.locator("#olderProjectConv").click();
      await page.waitForFunction(() => document.querySelector(".doc h1")?.textContent === "Valid fixture conversation");
      conversationNav.olderTitle = (await page.locator(".doc h1").innerText()).trim();
    }
    const validReaderText = await page.locator("#reader").innerText();
    if (validReaderText.includes("<local-command") || validReaderText.includes("<command-name>")
      || validReaderText.includes("Configured Terminal fixture settings")) {
      run.failures.push("embedded Claude local-command turns remained visible");
    }
    if (await page.locator(".turn").count() !== 2) run.failures.push("embedded local commands changed the visible turn count");
    const markdownTable = page.locator(".md-table-wrap");
    await markdownTable.waitFor({ state: "attached" });
    const tableTurn = page.locator(".turn", { has: markdownTable });
    if (await tableTurn.evaluate((node) => node.classList.contains("collapsed"))) {
      await tableTurn.locator(".turn-head").click();
    }
    await markdownTable.waitFor({ state: "visible" });
    const tableStructure = {
      rows: await markdownTable.locator("tbody tr").count(),
      headers: await markdownTable.locator("thead").count(),
      label: await markdownTable.getAttribute("aria-label"),
      focusable: await markdownTable.getAttribute("tabindex"),
    };
    if (tableStructure.rows !== 2 || tableStructure.headers !== 0) run.failures.push(`empty-header Markdown table rendered incorrectly: ${JSON.stringify(tableStructure)}`);
    if (!tableStructure.label || tableStructure.focusable !== "0") run.failures.push("Markdown table region is not keyboard accessible");
    if (!await markdownTable.locator("strong", { hasText: "ven-46" }).count()) run.failures.push("Markdown table inline formatting was lost");
    await page.setViewportSize({ width: 390, height: 844 });
    const mobileTable = await page.evaluate(() => {
      const wrapper = document.querySelector(".md-table-wrap");
      return {
        viewport: document.documentElement.clientWidth,
        page: document.documentElement.scrollWidth,
        clientWidth: wrapper.clientWidth,
        scrollWidth: wrapper.scrollWidth,
      };
    });
    if (mobileTable.page > mobileTable.viewport) run.failures.push(`Markdown table caused page overflow (${mobileTable.page} > ${mobileTable.viewport})`);
    if (mobileTable.scrollWidth <= mobileTable.clientWidth) run.failures.push("wide Markdown table is not locally scrollable on mobile");
    await page.setViewportSize({ width: 1365, height: 900 });
    await page.locator("#cbBackProject").click();

    const resumedRows = page.locator(".ph-conv-main", { hasText: "Resumed fixture conversation" });
    const resumedLineageRows = await resumedRows.count();
    if (resumedLineageRows !== 1) run.failures.push("resumed Claude lineage was not canonicalized to one row");
    else {
      await resumedRows.click();
      await page.waitForFunction(() => document.querySelectorAll('.turn[data-type="tool"]').length === 1);
      const resumedText = await page.locator("#reader").innerText();
      if (!resumedText.includes("Newest branch remains visible.")) run.failures.push("newest resumed Claude branch was not selected");
      if (resumedText.includes("Old branch should be superseded.")) run.failures.push("superseded Claude branch remained visible");
      if (await page.locator('.turn[data-type="tool"] .tool-result').count() !== 1) {
        run.failures.push("tool call and result were not rendered as one execution");
      }
      const toolVisibility = page.locator("#toggleTools");
      if (!await toolVisibility.count()) run.failures.push("conversation tool-visibility toggle is missing");
      else {
        const hideLabel = (await toolVisibility.innerText()).trim();
        if (!/Hide tools|Ocultar herramientas/.test(hideLabel)) run.failures.push(`unexpected hide-tools label: ${hideLabel}`);
        await toolVisibility.focus();
        await toolVisibility.press("Enter");
        await page.waitForFunction(() => document.querySelectorAll('.turn[data-type="tool"]').length === 0);
        const showLabel = (await page.locator("#toggleTools").innerText()).trim();
        if (!/Show tools|Mostrar herramientas/.test(showLabel)) run.failures.push(`unexpected show-tools label: ${showLabel}`);
        if (!await page.locator('.cb-count[data-type="tool"].off').count()) run.failures.push("tool count did not reflect hidden state");
        await page.locator("#toggleTools").click();
        await page.waitForFunction(() => document.querySelectorAll('.turn[data-type="tool"]').length === 1);
      }
      await page.locator("#cbBackProject").click();
    }

    await page.locator(".ph-conv-main", { hasText: "Parent fixture conversation" }).click();
    await page.waitForFunction(() => document.querySelectorAll(".subagent-node").length === 2);
    const jumpLastTurn = page.locator("#jumpLastTurn");
    if (!await jumpLastTurn.count()) run.failures.push("last-turn jump action is missing");
    else {
      const jumpLabel = await jumpLastTurn.getAttribute("aria-label");
      if (!/last turn|último turno/i.test(jumpLabel || "")) run.failures.push(`unexpected last-turn jump label: ${jumpLabel}`);
      await page.setViewportSize({ width: 1365, height: 500 });
      await page.locator("#reader").evaluate((node) => { node.scrollTop = 0; });
      await jumpLastTurn.click();
      await page.waitForTimeout(450);
      const jumpState = await page.evaluate(() => {
        const reader = document.querySelector("#reader");
        const turns = [...reader.querySelectorAll("#conversationTurns .turn")].filter((turn) => turn.getClientRects().length);
        return { scrollTop: Math.round(reader.scrollTop), visibleTurns: turns.length };
      });
      if (jumpState.visibleTurns && jumpState.scrollTop <= 0) run.failures.push(`last-turn jump did not scroll the conversation: ${JSON.stringify(jumpState)}`);
      await page.setViewportSize({ width: 1365, height: 900 });
    }
    const instructionLayout = async () => {
      const instruction = page.locator('.turn[data-kind="instruction"]');
      if (!await instruction.count()) return null;
      if (!await instruction.evaluate((node) => node.classList.contains("collapsed"))) {
        await instruction.locator(".turn-head").click();
      }
      return instruction.evaluate((node) => {
        const tag = node.querySelector(".tag").getBoundingClientRect();
        const preview = node.querySelector(".preview").getBoundingClientRect();
        return {
          label: node.querySelector(".tag").textContent.trim(),
          tagRight: Math.round(tag.right * 10) / 10,
          previewLeft: Math.round(preview.left * 10) / 10,
          overlaps: tag.right > preview.left + 0.5,
        };
      });
    };
    const instructionLayouts = [];
    instructionLayouts.push({ viewport: "desktop", lang: "initial", ...(await instructionLayout()) });
    await page.locator("#btnLang").click();
    instructionLayouts.push({ viewport: "desktop", lang: "alternate", ...(await instructionLayout()) });
    if (!/Ocultar herramientas/.test((await page.locator("#toggleTools").innerText()).trim())) {
      run.failures.push("Spanish tool-visibility label is missing");
    }
    if (!/Ir al último turno/i.test(await page.locator("#jumpLastTurn").getAttribute("aria-label") || "")) {
      run.failures.push("Spanish last-turn jump label is missing");
    }
    if (!/Más reciente/.test((await page.locator("#newerProjectConv").innerText()).trim())
      || !/Más antigua/.test((await page.locator("#olderProjectConv").innerText()).trim())) {
      run.failures.push("Spanish newer/older navigation labels are missing");
    }
    await page.locator("#btnLang").click();
    if (!/Hide tools/.test((await page.locator("#toggleTools").innerText()).trim())) {
      run.failures.push("English tool-visibility label is missing");
    }
    if (instructionLayouts.some((layout) => layout.overlaps)) {
      run.failures.push(`instruction tag overlaps preview: ${JSON.stringify(instructionLayouts)}`);
    }
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

    await page.locator("#btnAnalytics").click();
    await page.waitForFunction(() => document.querySelector("#analytics")?.style.display === "block");
    await page.locator("#analytics").evaluate((node) => { node.scrollTop = 420; });
    await page.waitForTimeout(50);
    const analyticsToolbarState = await page.evaluate(() => {
      const view = document.querySelector("#analytics");
      const toolbar = view.querySelector(":scope > .view-sticky");
      const viewRect = view.getBoundingClientRect();
      const toolbarRect = toolbar.getBoundingClientRect();
      return {
        position: getComputedStyle(toolbar).position,
        scrollTop: Math.round(view.scrollTop),
        topDelta: Math.round((toolbarRect.top - viewRect.top) * 10) / 10,
      };
    });
    if (analyticsToolbarState.position !== "sticky" || analyticsToolbarState.scrollTop <= 0 || Math.abs(analyticsToolbarState.topDelta) > 1) {
      run.failures.push(`analytics toolbar did not remain sticky: ${JSON.stringify(analyticsToolbarState)}`);
    }
    await page.locator("#btnCloseAnalytics").click();

    await page.setViewportSize({ width: 390, height: 844 });
    instructionLayouts.push({ viewport: "mobile", lang: "initial", ...(await instructionLayout()) });
    await page.locator("#btnLang").click();
    instructionLayouts.push({ viewport: "mobile", lang: "alternate", ...(await instructionLayout()) });
    await page.locator("#btnLang").click();
    if (instructionLayouts.slice(-2).some((layout) => layout.overlaps)) {
      run.failures.push(`mobile instruction tag overlaps preview: ${JSON.stringify(instructionLayouts.slice(-2))}`);
    }
    const mobileLayout = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      page: document.documentElement.scrollWidth,
      targets: [...document.querySelectorAll(".subagent-toggle")].every((node) => node.getBoundingClientRect().height >= 44),
      toolToggleTarget: document.querySelector("#toggleTools")?.getBoundingClientRect().height >= 44,
      jumpTarget: document.querySelector("#jumpLastTurn")?.getBoundingClientRect().height >= 44,
    }));
    if (mobileLayout.page > mobileLayout.viewport) run.failures.push(`mobile layout overflows horizontally (${mobileLayout.page} > ${mobileLayout.viewport})`);
    if (!mobileLayout.targets) run.failures.push("subagent disclosure touch target is below 44px on mobile");
    if (!mobileLayout.toolToggleTarget) run.failures.push("tool-visibility toggle touch target is below 44px on mobile");
    if (!mobileLayout.jumpTarget) run.failures.push("last-turn jump touch target is below 44px on mobile");

    run.subagentHierarchy = {
      rootConversations: projectRows.length,
      linkedSubagents: 3,
      orphanVisible: !!await orphanRow.count(),
      resumedLineageRows,
      toolVisibilityToggle: true,
      lastTurnJump: true,
      conversationNav,
      projectToolbar: projectToolbarState,
      analyticsToolbar: analyticsToolbarState,
      markdownTable: { ...tableStructure, mobile: mobileTable },
      mobileLayout,
      instructionLayouts,
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

  const analyticsButton = page.locator("#btnAnalytics");
  if (await analyticsButton.count()) await analyticsButton.click();
  await page.waitForTimeout(150);
  const tokenCard = page.locator(".an-card", { hasText: /Tokens by model|Tokens por modelo/ });
  const tokenLabels = await tokenCard.locator(".an-summary .lbl").allTextContents();
  const tokenAccounting = {
    labels: tokenLabels.map((label) => label.trim()),
    models: await tokenCard.locator(".lg-bar-row").count(),
    legacyNote: await tokenCard.locator(".lg-sub").count() > 0,
  };
  if (!tokenAccounting.labels.some((label) => /processed tokens|tokens procesados/i.test(label))
    || !tokenAccounting.labels.some((label) => /cached input|entrada en caché/i.test(label))
    || !tokenAccounting.labels.some((label) => /fresh input \+ output|entrada fresca \+ salida/i.test(label))) {
    run.failures.push(`token accounting labels are not comparable: ${JSON.stringify(tokenAccounting)}`);
  }
  if (!tokenAccounting.models || tokenAccounting.legacyNote) {
    run.failures.push(`normalized demo token accounting is incomplete: ${JSON.stringify(tokenAccounting)}`);
  }
  run.tokenAccounting = tokenAccounting;
  await page.locator("#btnCloseAnalytics").click();

  const projectsButton = page.locator("#btnProjects");
  if (await projectsButton.count()) await projectsButton.click();
  await page.waitForTimeout(250);

  const demoLayout = await page.evaluate(() => {
    const banner = document.querySelector("#demoBanner").getBoundingClientRect();
    const topbar = document.querySelector(".topbar").getBoundingClientRect();
    const shell = document.querySelector(".shell").getBoundingClientRect();
    return {
      bannerHeight: Math.round(banner.height),
      topbarHeight: Math.round(topbar.height),
      shellTop: Math.round(shell.top),
      topbarBottom: Math.round(topbar.bottom),
    };
  });
  if (demoLayout.topbarHeight > 80) run.failures.push(`demo topbar is oversized (${demoLayout.topbarHeight}px)`);
  if (Math.abs(demoLayout.shellTop - demoLayout.topbarBottom) > 1) {
    run.failures.push(`demo shell does not follow the topbar (${demoLayout.shellTop}px vs ${demoLayout.topbarBottom}px)`);
  }
  run.layout = demoLayout;

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
