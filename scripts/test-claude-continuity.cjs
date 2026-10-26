#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const repo = path.resolve(__dirname, "..");
const converter = path.join(repo, "converters", "convert_claude.py");
const ledger = path.join(repo, "converters", "extract_ledger.py");
const reviewPlan = path.join(repo, "converters", "plan_reviews.py");
const reviewPlanEval = path.join(repo, "converters", "eval_review_plan.py");
const viewer = path.join(repo, "viewer.html");
const docsViewer = path.join(repo, "docs", "index.html");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-claude-continuity-"));

const ids = {
  old: "11111111-1111-4111-8111-111111111111",
  resumed: "22222222-2222-4222-8222-222222222222",
  distinct: "33333333-3333-4333-8333-333333333333",
  local: "44444444-4444-4444-8444-444444444444",
  configUi: "55555555-5555-4555-8555-555555555555",
  lineage: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
};
const cwd = "/Users/test/code/CascadeProjects/facturante-conversion";

function row(type, sessionId, uuid, parentUuid, timestamp, content) {
  const role = type === "assistant" ? "assistant" : "user";
  return {
    type,
    cwd,
    sessionId,
    uuid,
    parentUuid,
    timestamp,
    message: {
      role,
      ...(role === "assistant" ? {
        model: "claude-fixture",
        usage: { input_tokens: 8, output_tokens: 3 },
      } : {}),
      content,
    },
  };
}

function writeJsonl(file, rows) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, rows.map((item) => JSON.stringify(item)).join("\n") + "\n");
}

function run(command, args) {
  return execFileSync(command, args, { cwd: repo, encoding: "utf8" });
}

function markdownById(outDir) {
  const result = new Map();
  for (const name of fs.readdirSync(path.join(outDir, "facturante-conversion"))) {
    if (!name.endsWith(".md")) continue;
    const file = path.join(outDir, "facturante-conversion", name);
    const text = fs.readFileSync(file, "utf8");
    const match = text.match(/(?:^|\|)\s*id\s*:\s*([^|]*?)\s*(?=\||$)/i);
    if (match) result.set(match[1].trim(), { file, text });
  }
  return result;
}

function viewerHelpers(source) {
  const parseStart = source.indexOf("function parseTurns");
  const parseEnd = source.indexOf("function previewText", parseStart);
  assert(parseStart >= 0 && parseEnd > parseStart, "viewer tool helpers are missing");
  const parseTurns = new Function(
    `${source.slice(parseStart, parseEnd)}\nreturn parseTurns;`,
  )();

  const stableStart = source.indexOf("function stableSessionKey");
  const stableEnd = source.indexOf("function mergeSupersededProgress", stableStart);
  assert(stableStart >= 0 && stableEnd > stableStart, "viewer lineage helpers are missing");
  const lineage = new Function(
    `${source.slice(stableStart, stableEnd)}\nreturn {stableSessionKey,newerSession};`,
  )();

  const internalStart = source.indexOf("function internalClaudeLocalCommandTurn");
  const internalEnd = source.indexOf("function cleanSessionTitleCandidate", internalStart);
  assert(internalStart >= 0 && internalEnd > internalStart, "viewer local-command helper is missing");
  const internal = new Function(
    `${source.slice(internalStart, internalEnd)}\nreturn {internalClaudeLocalCommand,withoutClaudeLocalCommandTurns};`,
  )();
  return { parseTurns, ...lineage, ...internal };
}

try {
  const rawRoot = path.join(tmp, "raw");
  const rawProject = path.join(rawRoot, "-Users-test-code-CascadeProjects-facturante-conversion");
  const outDir = path.join(tmp, "markdown-claude");
  const rootUser = row(
    "user", ids.old, ids.lineage, null, "2026-07-30T10:00:00Z", "Inspect the billing flow.",
  );
  const toolCall = row(
    "assistant", ids.old, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab", ids.lineage,
    "2026-07-30T10:01:00Z",
    [{ type: "tool_use", name: "Bash", input: { command: "python3 scripts/check.py" } }],
  );
  const toolResult = row(
    "user", ids.old, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaac",
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab", "2026-07-30T10:02:00Z",
    [{ type: "tool_result", content: "checks passed" }],
  );
  rootUser.entrypoint = "cli";
  writeJsonl(path.join(rawProject, `${ids.old}.jsonl`), [rootUser, toolCall, toolResult]);

  writeJsonl(path.join(rawProject, `${ids.resumed}.jsonl`), [
    { ...rootUser, sessionId: ids.resumed },
    { ...toolCall, sessionId: ids.resumed },
    { ...toolResult, sessionId: ids.resumed },
    row(
      "user", ids.resumed, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaae",
      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaac", "2026-07-31T11:59:00Z",
      "<local-command-stdout>token=internal-secret-value</local-command-stdout>",
    ),
    row(
      "assistant", ids.resumed, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaad",
      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaae", "2026-07-31T12:00:00Z",
      [{ type: "text", text: "The resumed investigation is complete." }],
    ),
    row(
      "user", ids.resumed, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaf",
      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaad", "2026-07-31T12:01:00Z",
      "<local-command-stdout>Model changed.</local-command-stdout>",
    ),
  ]);

  writeJsonl(path.join(rawProject, `${ids.distinct}.jsonl`), [
    row(
      "user", ids.distinct, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", null,
      "2026-07-30T11:00:00Z", "Inspect the billing flow.",
    ),
    row(
      "assistant", ids.distinct, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbc",
      "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "2026-07-30T11:01:00Z",
      [{ type: "text", text: "This is an independent conversation with the same title." }],
    ),
  ]);

  writeJsonl(path.join(rawProject, `${ids.local}.jsonl`), [
    row(
      "user", ids.local, "cccccccc-cccc-4ccc-8ccc-cccccccccccc", null,
      "2026-07-31T09:00:00Z",
      "<local-command-caveat>Generated local command wrapper.</local-command-caveat>",
    ),
    row(
      "user", ids.local, "cccccccc-cccc-4ccc-8ccc-cccccccccccd",
      "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "2026-07-31T09:00:01Z",
      "<command-name>/config</command-name> <command-message>config</command-message>",
    ),
    row(
      "user", ids.local, "cccccccc-cccc-4ccc-8ccc-ccccccccccce",
      "cccccccc-cccc-4ccc-8ccc-cccccccccccd", "2026-07-31T09:00:02Z",
      "<local-command-stdout>Set notifications.</local-command-stdout>",
    ),
  ]);

  writeJsonl(path.join(rawProject, `${ids.configUi}.jsonl`), [
    row(
      "user", ids.configUi, "dddddddd-dddd-4ddd-8ddd-dddddddddddd", null,
      "2026-07-31T09:10:00Z", "config",
    ),
    row(
      "assistant", ids.configUi, "dddddddd-dddd-4ddd-8ddd-ddddddddddde",
      "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "2026-07-31T09:10:01Z",
      [{ type: "thinking", thinking: "" }],
    ),
    row(
      "assistant", ids.configUi, "dddddddd-dddd-4ddd-8ddd-dddddddddddf",
      "dddddddd-dddd-4ddd-8ddd-ddddddddddde", "2026-07-31T09:10:02Z",
      [{ type: "tool_use", name: "AskUserQuestion", input: { questions: [] } }],
    ),
    row(
      "user", ids.configUi, "dddddddd-dddd-4ddd-8ddd-dddddddddd01",
      "dddddddd-dddd-4ddd-8ddd-dddddddddddf", "2026-07-31T09:10:03Z",
      [{ type: "tool_result", content: "settings selected" }],
    ),
    row(
      "user", ids.configUi, "dddddddd-dddd-4ddd-8ddd-dddddddddd02",
      "dddddddd-dddd-4ddd-8ddd-dddddddddd01", "2026-07-31T09:10:04Z",
      [{ type: "text", text: "Settings saved." }],
    ),
  ]);

  const projectOut = path.join(outDir, "facturante-conversion");
  fs.mkdirSync(projectOut, { recursive: true });
  const legacyLocal = path.join(projectOut, `_config__${ids.local.slice(0, 8)}.md`);
  fs.writeFileSync(
    legacyLocal,
    `# /config\n\n<!-- date: 2026-07-31T09:00:00Z | id: ${ids.local} | project: facturante-conversion | source: claude-code -->\n\n### You\n\n<local-command-caveat>Generated local command wrapper.</local-command-caveat>\n\n### You\n\n<command-name>/config</command-name>\n\n### You\n\n<local-command-stdout>Set notifications.</local-command-stdout>\n`,
  );
  const legacyConfigUi = path.join(projectOut, `_config_ui__${ids.configUi.slice(0, 8)}.md`);
  fs.writeFileSync(
    legacyConfigUi,
    `# config\n\n<!-- date: 2026-07-31T09:10:00Z | id: ${ids.configUi} | project: facturante-conversion | source: claude-code -->\n\n### You\n\nconfig\n\n### Claude\n\n[tool: AskUserQuestion {"questions": []}]\n\n### You\n\n[result]\n\n### You\n\nSettings saved.\n`,
  );

  const converterOutput = run("python3", [
    converter, rawRoot, outDir, "claude-code", path.join(tmp, "missing-history.jsonl"),
  ]);
  assert.match(converterOutput, /Ignored internal sessions: 2/);
  assert.match(converterOutput, /Marked existing internal Markdown: 2/);

  const markdown = markdownById(outDir);
  assert(markdown.has(ids.old), "the earlier branch was not preserved on disk");
  assert(markdown.has(ids.resumed), "the resumed branch was not converted");
  assert(markdown.has(ids.distinct), "the independent same-title session was not converted");
  assert.match(markdown.get(ids.local).text, /internal: true/);
  assert.match(markdown.get(ids.local).text, /internal_kind: local_command/);
  assert.match(markdown.get(ids.configUi).text, /internal: true/);
  assert.match(markdown.get(ids.configUi).text, /internal_kind: local_command/);
  assert.match(markdown.get(ids.old).text, new RegExp(`lineage_id: ${ids.lineage}`));
  assert.match(markdown.get(ids.resumed).text, new RegExp(`lineage_id: ${ids.lineage}`));
  assert.match(markdown.get(ids.resumed).text, /message_count: 6/);
  assert.match(markdown.get(ids.old).text, /\| client: cli -->/, "Claude entrypoint should become client metadata");
  assert.match(markdown.get(ids.old).text, /^### You <!-- at: 2026-07-30T10:00:00Z -->$/m, "turn headers should carry the message time");
  assert.match(markdown.get(ids.resumed).text, /\| client: cli -->/, "a resumed branch keeps the session's client");
  assert.match(markdown.get(ids.resumed).text, /internal-secret-value/,
    "the cumulative Markdown should preserve embedded local-command evidence");
  assert.match(markdown.get(ids.resumed).text, /updated_at: 2026-07-31T12:00:00Z/,
    "trailing local-command traffic should not advance conversation activity");

  const legacyProject = path.join(outDir, "conversion");
  fs.mkdirSync(legacyProject, { recursive: true });
  fs.writeFileSync(
    path.join(legacyProject, `legacy-${ids.old}.md`),
    markdown.get(ids.old).text
      .replace(/\s*\|\s*format_version:[^|]*\|\s*lineage_id:[^|]*\|\s*message_count:[^|]*\|\s*updated_at:[^>]*?(?=-->)/, " ")
      .replace("project: facturante-conversion", "project: conversion"),
  );

  run("python3", [ledger, rawRoot, outDir, "claude-code", "claude"]);
  const ledgerDoc = JSON.parse(fs.readFileSync(path.join(outDir, "_ledger.json"), "utf8"));
  assert.strictEqual(ledgerDoc.sources["claude-code"].totals.sessions, 2,
    "ledger should count one resumed lineage plus the independent same-title session");
  assert.strictEqual(ledgerDoc.sources["claude-code"].totals.user_messages, 2,
    "embedded local commands should not inflate user-message metrics");

  run("python3", [reviewPlan, tmp]);
  const plan = JSON.parse(fs.readFileSync(path.join(tmp, "_review_run_plan.json"), "utf8"));
  const conversationIds = (plan.input_manifest || [])
    .filter((item) => item.type === "conversation")
    .map((item) => item.id_or_path);
  assert.deepStrictEqual(new Set(conversationIds), new Set([ids.resumed, ids.distinct]));
  const resumedInput = (plan.input_manifest || []).find((item) => item.id_or_path === ids.resumed);
  assert(resumedInput, "resumed conversation is missing from the review plan");
  assert.strictEqual(resumedInput.possible_secret, false,
    "embedded local-command text should not enter review context");
  assert.strictEqual(resumedInput.preprocessed, true,
    "cleaned conversation text should be addressable by the review runtime");
  assert((resumedInput.sanitization_types || []).includes("local_command_turns"));
  const preprocessed = JSON.parse(fs.readFileSync(path.join(tmp, "_review_preprocessed_inputs.json"), "utf8"));
  const preprocessedKey = resumedInput.preprocessed_ref.split("#")[1];
  const reviewText = preprocessed.inputs[preprocessedKey].text;
  assert(!reviewText.includes("internal-secret-value"),
    "review runtime input retained an embedded local command");
  run("python3", [reviewPlanEval, tmp]);
  const planEval = JSON.parse(fs.readFileSync(path.join(tmp, "_review_eval_report.json"), "utf8"));
  assert.strictEqual(planEval.status, "pass");

  const toolMarkdown = [
    "# Tool grouping",
    "",
    "### Claude",
    "",
    "[tool: Bash]",
    "```bash",
    "python3 scripts/check.py",
    "```",
    "",
    "### You",
    "",
    "[result]",
    "```",
    "checks passed",
    "```",
    "",
    "### Claude",
    "",
    "Done.",
  ].join("\n");

  for (const file of [viewer, docsViewer]) {
    const helpers = viewerHelpers(fs.readFileSync(file, "utf8"));
    const turns = helpers.parseTurns(toolMarkdown);
    assert.strictEqual(turns.length, 2, `${path.basename(file)} left tool result as a separate turn`);
    assert.strictEqual(turns[0].toolKind, "call");
    assert.match(turns[0].resultMd, /checks passed/);
    assert.deepStrictEqual(turns[0].progressKeys, [0, 1]);
    assert.strictEqual(
      helpers.stableSessionKey({ fuente: "claude-code", sessionId: ids.old, lineageId: ids.lineage }),
      helpers.stableSessionKey({ fuente: "claude-code", sessionId: ids.resumed, lineageId: ids.lineage }),
    );
    assert(helpers.newerSession(
      { updatedAt: "2026-07-31T12:00:00Z", messageCount: 5 },
      { updatedAt: "2026-07-30T10:02:00Z", messageCount: 3 },
    ));
    assert(helpers.internalClaudeLocalCommand(
      { fuente: "claude-code" },
      [{ type: "user", md: "<command-name>/config</command-name>" }],
    ));
    assert(helpers.internalClaudeLocalCommand(
      { fuente: "claude-code" },
      [
        { type: "user", md: "config" },
        { type: "tool", label: "tool: AskUserQuestion", md: "", resultMd: "settings selected" },
        { type: "user", md: "Settings saved." },
      ],
      "config",
    ));
    assert(!helpers.internalClaudeLocalCommand(
      { fuente: "claude-code" },
      [
        { type: "user", md: "<command-name>/config</command-name>" },
        { type: "assistant", md: "Here is what the command does." },
      ],
      "config",
    ));
    const visibleTurns = helpers.withoutClaudeLocalCommandTurns(
      { fuente: "claude-code" },
      [
        { type: "user", md: "Keep this request.", progressKeys: [0] },
        { type: "user", md: "<command-name>/model</command-name>", progressKeys: [1] },
        { type: "user", md: "<local-command-stdout>Model changed.</local-command-stdout>", progressKeys: [2] },
        { type: "assistant", md: "Keep this response.", progressKeys: [3] },
      ],
    );
    assert.deepStrictEqual(visibleTurns.map((turn) => turn.progressKeys[0]), [0, 3]);
    assert.strictEqual(helpers.withoutClaudeLocalCommandTurns(
      { fuente: "codex" },
      [{ type: "user", md: "<command-name>/model</command-name>" }],
    ).length, 1, "non-Claude transcripts should remain untouched");
  }

  console.log("Claude continuity, local-command filtering, and tool grouping: ok");
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
