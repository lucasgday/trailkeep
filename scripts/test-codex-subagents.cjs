#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const CONVERTER = path.join(ROOT, "converters", "convert_codex.py");
const LEDGER = path.join(ROOT, "converters", "extract_ledger.py");
const REVIEW_PLAN = path.join(ROOT, "converters", "plan_reviews.py");
const BACKUP = path.join(ROOT, "update-backup.sh");
const VIEWER = path.join(ROOT, "viewer.html");

const IDS = {
  parent: "11111111-1111-4111-8111-111111111111",
  detail: "22222222-2222-4222-8222-222222222222",
  tests: "33333333-3333-4333-8333-333333333333",
  nested: "44444444-4444-4444-8444-444444444444",
  orphan: "55555555-5555-4555-8555-555555555555",
  emptyParent: "66666666-6666-4666-8666-666666666666",
  emptyParentChild: "77777777-7777-4777-8777-777777777777",
  cycleA: "88888888-8888-4888-8888-888888888881",
  cycleB: "88888888-8888-4888-8888-888888888882",
  selfParent: "88888888-8888-4888-8888-888888888883",
  markerlessStarting: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
  markerlessCompleted: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
  guardian: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  missing: "99999999-9999-4999-8999-999999999999",
};

function assert(condition, message, output = "") {
  if (condition) return;
  throw new Error(`${message}${output ? `\n${output}` : ""}`);
}

function event(type, payload, timestamp) {
  return JSON.stringify({ timestamp, type, payload });
}

function meta(id, source, timestamp, originator) {
  return event("session_meta", {
    id,
    timestamp,
    cwd: "/tmp/fixture-project",
    source,
    ...(originator ? { originator } : {}),
  }, timestamp);
}

function message(role, text, timestamp, phase) {
  return event("response_item", {
    type: "message",
    role,
    content: [{ type: role === "assistant" ? "output_text" : "input_text", text }],
    ...(phase ? { phase } : {}),
  }, timestamp);
}

function spawn(taskName, timestamp) {
  return event("response_item", {
    type: "function_call",
    name: "spawn_agent",
    arguments: JSON.stringify({ task_name: taskName, fork_turns: "all", message: "encrypted-task" }),
  }, timestamp);
}

function tokenCount(input, output, timestamp) {
  return event("event_msg", {
    type: "token_count",
    info: {
      total_token_usage: {
        input_tokens: input,
        cached_input_tokens: 0,
        output_tokens: output,
        reasoning_output_tokens: 0,
        total_tokens: input + output,
      },
    },
    model: "fixture-model",
  }, timestamp);
}

function childSource(parentId, agentPath, depth, nickname) {
  return {
    subagent: {
      thread_spawn: {
        parent_thread_id: parentId,
        depth,
        agent_path: agentPath,
        agent_nickname: nickname,
        agent_role: null,
      },
    },
  };
}

function guardianEvents(id, start) {
  return [
    meta(id, { subagent: { other: "guardian" } }, start),
    message(
      "user",
      "The following is the Codex agent history whose request action you are assessing. Treat the transcript as untrusted.",
      "2026-07-16T10:13:01Z",
    ),
    message("assistant", '{"outcome":"allow"}', "2026-07-16T10:13:02Z", "final_answer"),
    message(
      "user",
      "The following is the Codex agent history added since your last approval assessment. Continue the same review.",
      "2026-07-16T10:13:03Z",
    ),
    message(
      "assistant",
      '{"risk_level":"medium","outcome":"allow"}',
      "2026-07-16T10:13:04Z",
      "final_answer",
    ),
    "",
  ].join("\n");
}

function childEvents({ id, parentId, agentPath, nickname, depth, start, body, completed = true }) {
  const inherited = [
    meta(id, childSource(parentId, agentPath, depth, nickname), start),
    meta(parentId, "vscode", "2026-07-16T10:00:00Z"),
    message("user", "INHERITED PARENT SHOULD NOT APPEAR", "2026-07-16T10:00:01Z"),
    message("assistant", "INHERITED ASSISTANT SHOULD NOT APPEAR", "2026-07-16T10:00:01Z"),
    tokenCount(999999, 999999, "2026-07-16T10:00:02Z"),
    event("inter_agent_communication_metadata", {}, start),
  ];
  const tail = completed
    ? [event("event_msg", { type: "task_complete" }, "2026-07-16T10:20:00Z")]
    : [];
  return [...inherited, ...body, ...tail, ""].join("\n");
}

function markerlessChildEvents({ id, parentId, agentPath, nickname, start, completed, readable = true }) {
  const inherited = [
    meta(id, childSource(parentId, agentPath, 1, nickname), start),
    meta(parentId, "vscode", "2026-07-16T09:00:00Z"),
    event("event_msg", { type: "task_started" }, "2026-07-16T09:00:00Z"),
    message("user", "MARKERLESS INHERITED USER MUST NOT APPEAR", "2026-07-16T09:00:01Z"),
    message("assistant", "MARKERLESS INHERITED ASSISTANT MUST NOT APPEAR", "2026-07-16T09:00:02Z"),
    tokenCount(888888, 888888, "2026-07-16T09:00:03Z"),
    event("event_msg", { type: "task_complete" }, "2026-07-16T09:00:04Z"),
    event("event_msg", { type: "task_started" }, start),
  ];
  const childTail = completed && readable
    ? [
        message("user", "Markerless child task", "2026-07-16T10:10:01Z"),
        message("assistant", "Markerless child result is preserved.", "2026-07-16T10:10:02Z", "final_answer"),
        tokenCount(15, 5, "2026-07-16T10:10:03Z"),
        event("event_msg", { type: "task_complete" }, "2026-07-16T10:10:04Z"),
      ]
    : completed
      ? [event("event_msg", { type: "task_complete" }, "2026-07-16T10:10:04Z")]
      : [
        message("developer", "Markerless child setup only", "2026-07-16T10:10:01Z"),
        event("event_msg", { type: "turn_aborted" }, "2026-07-16T10:10:02Z"),
      ];
  return [...inherited, ...childTail, ""].join("\n");
}

function writeFixtures(sessions) {
  fs.mkdirSync(sessions, { recursive: true });
  const parent = [
    meta(IDS.parent, "vscode", "2026-07-16T10:00:00Z", "codex_cli_rs"),
    message("user", "Build the parent dossier", "2026-07-16T10:00:01Z"),
    message("assistant", "I will delegate the audits.", "2026-07-16T10:00:02Z", "commentary"),
    spawn("detail_audit", "2026-07-16T10:00:03Z"),
    spawn("test_scope", "2026-07-16T10:00:04Z"),
    tokenCount(100, 20, "2026-07-16T10:00:05Z"),
    message("assistant", "Parent complete.", "2026-07-16T10:00:06Z", "final_answer"),
    event("event_msg", { type: "task_complete" }, "2026-07-16T10:00:07Z"),
    "",
  ].join("\n");

  const detail = childEvents({
    id: IDS.detail,
    parentId: IDS.parent,
    agentPath: "/root/detail_audit",
    nickname: "Ada",
    depth: 1,
    start: "2026-07-16T10:01:00Z",
    body: [
      message("assistant", "Auditing the detail contract.", "2026-07-16T10:01:01Z", "commentary"),
      event("response_item", { type: "custom_tool_call", name: "exec", input: JSON.stringify({ command: "pnpm test" }) }, "2026-07-16T10:01:02Z"),
      event("response_item", { type: "custom_tool_call_output", output: { exit_code: 0, output: "tests passed" } }, "2026-07-16T10:01:03Z"),
      event("compacted", { replacement_history: [
        { type: "message", role: "user", content: [{ type: "input_text", text: "INHERITED PARENT SHOULD NOT APPEAR" }] },
        { type: "message", role: "assistant", content: [{ type: "output_text", text: "INHERITED ASSISTANT SHOULD NOT APPEAR" }] },
        { type: "message", role: "assistant", content: [{ type: "output_text", text: "COMPACTED CHILD EVIDENCE STAYS" }] },
        { type: "compaction", encrypted_content: "fixture" },
      ] }, "2026-07-16T10:01:03Z"),
      spawn("nested_check", "2026-07-16T10:01:04Z"),
      tokenCount(200, 40, "2026-07-16T10:01:05Z"),
      message("assistant", "Detail contract is sound.", "2026-07-16T10:01:06Z", "final_answer"),
    ],
  });

  const tests = childEvents({
    id: IDS.tests,
    parentId: IDS.parent,
    agentPath: "/root/test_scope",
    nickname: "Grace",
    depth: 1,
    start: "2026-07-16T10:02:00Z",
    completed: false,
    body: [
      message("assistant", "Checking test scope.", "2026-07-16T10:02:01Z", "commentary"),
      event("response_item", { type: "custom_tool_call", name: "exec", input: "const r = await tools.exec_command({ cmd: \"rg -n test .\" });" }, "2026-07-16T10:02:02Z"),
      tokenCount(50, 10, "2026-07-16T10:02:03Z"),
    ],
  });

  const nested = childEvents({
    id: IDS.nested,
    parentId: IDS.detail,
    agentPath: "/root/detail_audit/nested_check",
    nickname: "Linus",
    depth: 2,
    start: "2026-07-16T10:03:00Z",
    body: [
      message("assistant", "Nested evidence checked.", "2026-07-16T10:03:01Z", "final_answer"),
      tokenCount(30, 5, "2026-07-16T10:03:02Z"),
    ],
  });

  const orphan = childEvents({
    id: IDS.orphan,
    parentId: IDS.missing,
    agentPath: "/root/orphan_audit",
    nickname: "Katherine",
    depth: 1,
    start: "2026-07-16T10:04:00Z",
    body: [
      message("assistant", "Orphan evidence remains browsable.", "2026-07-16T10:04:01Z", "final_answer"),
      tokenCount(25, 5, "2026-07-16T10:04:02Z"),
    ],
  });

  const emptyParent = [
    meta(IDS.emptyParent, "vscode", "2026-07-16T10:05:00Z"),
    tokenCount(500, 50, "2026-07-16T10:05:01Z"),
    "",
  ].join("\n");

  const emptyParentChild = childEvents({
    id: IDS.emptyParentChild,
    parentId: IDS.emptyParent,
    agentPath: "/root/only_browsable_child",
    nickname: "Margaret",
    depth: 1,
    start: "2026-07-16T10:06:00Z",
    body: [
      message("assistant", "The child remains visible when its empty parent is skipped.", "2026-07-16T10:06:01Z", "final_answer"),
      tokenCount(20, 5, "2026-07-16T10:06:02Z"),
    ],
  });

  const cycleA = childEvents({
    id: IDS.cycleA,
    parentId: IDS.cycleB,
    agentPath: "/root/cycle_a",
    nickname: "Cycle A",
    depth: 1,
    start: "2026-07-16T10:07:00Z",
    body: [message("assistant", "Cycle A remains browsable as an orphan root.", "2026-07-16T10:07:01Z", "final_answer")],
  });

  const cycleB = childEvents({
    id: IDS.cycleB,
    parentId: IDS.cycleA,
    agentPath: "/root/cycle_b",
    nickname: "Cycle B",
    depth: 1,
    start: "2026-07-16T10:08:00Z",
    body: [message("assistant", "Cycle B remains browsable as an orphan root.", "2026-07-16T10:08:01Z", "final_answer")],
  });

  const selfParent = childEvents({
    id: IDS.selfParent,
    parentId: IDS.selfParent,
    agentPath: "/root/self_parent",
    nickname: "Self parent",
    depth: 1,
    start: "2026-07-16T10:09:00Z",
    body: [message("assistant", "A self-parent relation remains browsable as an orphan root.", "2026-07-16T10:09:01Z", "final_answer")],
  });

  const markerlessStarting = markerlessChildEvents({
    id: IDS.markerlessStarting,
    parentId: IDS.parent,
    agentPath: "/root/markerless_starting",
    nickname: "Starting child",
    start: "2026-07-16T10:10:00Z",
    completed: false,
  });

  const markerlessCompleted = markerlessChildEvents({
    id: IDS.markerlessCompleted,
    parentId: IDS.parent,
    agentPath: "/root/markerless_completed",
    nickname: "Completed child",
    start: "2026-07-16T10:10:00Z",
    completed: true,
  });

  const guardian = guardianEvents(IDS.guardian, "2026-07-16T10:13:00Z");

  const files = {
    parent, detail, tests, nested, orphan, emptyParent, emptyParentChild,
    cycleA, cycleB, selfParent, markerlessStarting, markerlessCompleted, guardian,
  };
  for (const [name, content] of Object.entries(files)) {
    fs.writeFileSync(path.join(sessions, `rollout-${name}.jsonl`), content);
  }
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    ...options,
  });
  const output = `${result.stdout || ""}${result.stderr || ""}`;
  assert(result.status === 0, `${path.basename(command)} exited ${result.status}`, output);
  return output;
}

function markdowns(output) {
  const found = [];
  for (const dirent of fs.readdirSync(output, { withFileTypes: true })) {
    const abs = path.join(output, dirent.name);
    if (dirent.isDirectory()) found.push(...markdowns(abs));
    else if (dirent.name.endsWith(".md")) found.push(abs);
  }
  return found;
}

function markdownById(files, id) {
  return files.find(file => fs.readFileSync(file, "utf8").includes(`id: ${id}`));
}

const temp = fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-codex-subagents-"));
try {
  const sessions = path.join(temp, "sessions");
  const output = path.join(temp, "markdown-codex");
  const index = path.join(temp, "session_index.jsonl");
  fs.writeFileSync(index, `${JSON.stringify({
    id: IDS.parent,
    thread_name: null,
    updated_at: "2026-07-01T10:00:00Z",
  })}\n`);
  writeFixtures(sessions);

  const converted = run("python3", [CONVERTER, sessions, index, output]);
  assert(/Converted: 10/.test(converted), "converter did not preserve all readable physical rollouts", converted);
  assert(/Subagents: 9/.test(converted), "converter did not report child rollouts separately", converted);
  assert(/Deferred subagents: 1/.test(converted), "converter did not safely defer the markerless starting snapshot", converted);
  assert(/Unreadable completed subagents: 0/.test(converted), "readable fixture was misclassified as completed-unreadable", converted);
  assert(/Ignored internal sessions: 1/.test(converted), "guardian rollout was not classified as internal", converted);
  assert(/Empty \(no readable messages\): 1/.test(converted), "converter did not report the unreadable parent rollout", converted);
  const files = markdowns(output);
  assert(files.length === 10, `expected 10 unique markdowns, found ${files.length}`);
  for (const id of Object.values(IDS).filter(id => ![IDS.missing, IDS.emptyParent, IDS.markerlessStarting, IDS.guardian].includes(id))) {
    assert(markdownById(files, id), `missing markdown for ${id}`);
  }

  const parentText = fs.readFileSync(markdownById(files, IDS.parent), "utf8");
  const detailText = fs.readFileSync(markdownById(files, IDS.detail), "utf8");
  const testsText = fs.readFileSync(markdownById(files, IDS.tests), "utf8");
  const nestedText = fs.readFileSync(markdownById(files, IDS.nested), "utf8");
  const markerlessText = fs.readFileSync(markdownById(files, IDS.markerlessCompleted), "utf8");
  assert(parentText.includes("[tool: spawn_agent → detail_audit]"), "parent is missing the stable child anchor");
  assert(parentText.includes("date: 2026-07-16T10:00:07Z"), "stale session index timestamp overrode the rollout's latest activity");
  assert(detailText.startsWith("# Detail audit\n"), "child title did not come from agent_path");
  assert(detailText.includes(`parent_id: ${IDS.parent}`), "child parent relation was not persisted");
  assert(detailText.includes("agent_status: completed"), "completed child status missing");
  assert(testsText.includes("agent_status: in_progress"), "in-progress snapshot status missing");
  assert(nestedText.includes(`parent_id: ${IDS.detail}`), "nested relation missing");
  assert(!detailText.includes("INHERITED PARENT SHOULD NOT APPEAR"), "forked parent history leaked into child markdown");
  assert(!detailText.includes("INHERITED ASSISTANT SHOULD NOT APPEAR"), "compaction reintroduced inherited assistant history");
  assert(detailText.includes("COMPACTED CHILD EVIDENCE STAYS"), "legitimate compacted child history was dropped");
  assert(detailText.includes("[tool: exec]"), "custom_tool_call was not converted");
  assert(detailText.includes("pnpm test"), "custom tool command body missing");
  assert(!detailText.includes("encrypted-task"), "spawn marker leaked the delegated task payload");
  assert(detailText.includes("format_version: 2"), "new Codex format version missing");
  assert(parentText.includes("client: cli"), "Codex CLI originator should become client metadata");
  const clientMap = spawnSync("python3", ["-c", [
    "import sys; sys.path.insert(0, sys.argv[1]); from convert_codex import client_from_meta as c",
    "print(c('Codex Desktop', 'vscode'), c('', 'vscode'), c('', 'exec'), c('codex-chrome-extension-sidepanel', 'vscode'), c('Codex Desktop', {'subagent': {}}) )",
  ].join("\n"), path.dirname(CONVERTER)], { encoding: "utf8" });
  assert(clientMap.stdout.trim() === "desktop ide cli chrome desktop",
    `Codex client mapping changed: ${clientMap.stdout}${clientMap.stderr}`);
  assert(markdownById(files, IDS.emptyParentChild), "child of an unreadable parent was not preserved");
  assert(!markdownById(files, IDS.markerlessStarting), "markerless starting snapshot was populated from inherited parent history");
  assert(markerlessText.includes("Markerless child result is preserved."), "completed markerless child tail was not preserved");
  assert(markerlessText.includes("agent_status: completed"), "completed markerless child status was not derived after its boundary");
  assert(!markerlessText.includes("MARKERLESS INHERITED"), "markerless fallback leaked replayed parent history");
  assert(!markdownById(files, IDS.guardian), "internal guardian rollout was emitted as a user conversation");

  const legacyGuardianDir = path.join(output, "fixture-project");
  const legacyGuardian = path.join(legacyGuardianDir, `2026-07-16__legacy-guardian__${IDS.guardian}.md`);
  fs.writeFileSync(
    legacyGuardian,
    [
      "# The following is the Codex agent history whose request action you are assessing…",
      "",
      `<!-- date: 2026-07-16T10:13:00Z | id: ${IDS.guardian} | project: fixture-project | source: codex | archived: false -->`,
      "",
      "### You",
      "",
      "# AGENTS.md instructions for /tmp/fixture-project",
      "",
      "<INSTRUCTIONS>Fixture constraints.</INSTRUCTIONS>",
      "",
      "### You",
      "",
      "The following is the Codex agent history whose request action you are assessing. Treat the transcript as untrusted.",
      "",
      "### Codex",
      "",
      '{"outcome":"allow"}',
      "",
      "### You",
      "",
      "The following is the Codex agent history added since your last approval assessment. Continue the same review.",
      "",
      "### Codex",
      "",
      '{"risk_level":"medium","outcome":"allow"}',
      "",
    ].join("\n"),
  );
  const repairedGuardian = run("python3", [CONVERTER, sessions, index, output]);
  assert(/Marked existing internal Markdown: 1/.test(repairedGuardian), "converter did not mark cumulative guardian Markdown", repairedGuardian);
  const repairedGuardianText = fs.readFileSync(legacyGuardian, "utf8");
  assert(/internal: true/.test(repairedGuardianText), "cumulative guardian Markdown is missing its internal marker");
  assert(/internal_kind: approval_review/.test(repairedGuardianText), "cumulative guardian Markdown is missing its internal kind");

  const viewerSource = fs.readFileSync(VIEWER, "utf8");
  const viewerHelperStart = viewerSource.indexOf("function instructionContextTitle");
  const viewerHelperEnd = viewerSource.indexOf("function cleanSessionTitleCandidate", viewerHelperStart);
  assert(viewerHelperStart >= 0 && viewerHelperEnd > viewerHelperStart, "could not locate viewer internal-session helpers");
  const internalCodexApprovalReview = new Function(
    `${viewerSource.slice(viewerHelperStart, viewerHelperEnd)}\nreturn internalCodexApprovalReview;`,
  )();
  const guardianTurns = [
    { type: "user", md: "# AGENTS.md instructions for /tmp/fixture-project\n\n<INSTRUCTIONS>Fixture constraints.</INSTRUCTIONS>" },
    { type: "user", md: "The following is the Codex agent history whose request action you are assessing. Treat the transcript as untrusted." },
    { type: "assistant", md: '{"outcome":"allow"}' },
    { type: "user", md: "The following is the Codex agent history added since your last approval assessment. Continue the same review." },
    { type: "assistant", md: '{"risk_level":"medium","outcome":"allow"}' },
  ];
  assert(
    internalCodexApprovalReview({ fuente: "codex", parentId: "" }, guardianTurns),
    "viewer did not hide a legacy guardian transcript",
  );
  assert(
    !internalCodexApprovalReview(
      { fuente: "codex", parentId: "" },
      [...guardianTurns, { type: "user", md: "Explain why this internal prompt appeared." }],
    ),
    "viewer hid a real conversation that discusses a guardian prompt",
  );

  const ledgerOutput = run("python3", [LEDGER, sessions, output, "codex", "codex"]);
  assert(/Ledger \[codex\]: 6 sessions/.test(ledgerOutput), "ledger did not count orphan and cyclic relations as roots", ledgerOutput);
  const ledger = JSON.parse(fs.readFileSync(path.join(output, "_ledger.json"), "utf8")).sources.codex;
  assert(ledger.totals.sessions === 6, `expected 6 root conversations, got ${ledger.totals.sessions}`);
  assert(ledger.totals.subagent_runs === 9, `expected 9 readable subagent runs, got ${ledger.totals.subagent_runs}`);
  assert(ledger.totals.tool_calls === 5, `expected 5 tool calls, got ${ledger.totals.tool_calls}`);
  assert(ledger.totals.test_runs === 1, `expected one child test run, got ${ledger.totals.test_runs}`);
  assert(ledger.totals.user_messages === 2, "inherited parent user messages leaked across a child boundary");
  assert(ledger.tokens.input < 1000, "inherited parent token snapshots were double-counted");

  run("python3", [REVIEW_PLAN, output]);
  const reviewPlan = JSON.parse(fs.readFileSync(path.join(output, "_review_run_plan.json"), "utf8"));
  assert(
    !(reviewPlan.input_manifest || []).some(item => item.id_or_path === IDS.guardian),
    "review preflight included a legacy guardian transcript",
  );

  const cachePath = path.join(output, "_ledger-cache.json");
  const legacyCache = JSON.parse(fs.readFileSync(cachePath, "utf8"));
  const baselineTokens = JSON.stringify(ledger.tokens);
  const baselineModels = JSON.stringify(ledger.tokens_by_model);
  legacyCache.version = 4;
  for (const entry of Object.values(legacyCache.sessions || {})) {
    if (!entry || !entry.metrics) continue;
    delete entry.metrics.parent_id;
    delete entry.metrics.subagent_runs;
  }
  fs.writeFileSync(cachePath, JSON.stringify(legacyCache, null, 2));
  const prunedSessions = path.join(temp, "sessions-pruned");
  fs.cpSync(sessions, prunedSessions, { recursive: true });
  fs.rmSync(path.join(prunedSessions, "rollout-detail.jsonl"));
  run("python3", [LEDGER, prunedSessions, output, "codex", "codex"]);
  const migratedDoc = JSON.parse(fs.readFileSync(path.join(output, "_ledger.json"), "utf8")).sources.codex;
  const migratedCache = JSON.parse(fs.readFileSync(cachePath, "utf8"));
  assert(migratedCache.version === 10, "legacy ledger cache was not upgraded after the safe carry");
  assert(JSON.stringify(migratedDoc.tokens) === baselineTokens, "v4 migration lost raw-pruned token metrics");
  assert(JSON.stringify(migratedDoc.tokens_by_model) === baselineModels, "v4 migration lost raw-pruned model metrics");
  assert(migratedDoc.totals.sessions === 6, "legacy carry lost child-parent root attribution");
  assert(migratedDoc.totals.subagent_runs === 9, "legacy carry lost the child execution count");

  const home = path.join(temp, "home");
  const liveSessions = path.join(home, ".codex", "sessions", "2026", "07", "16");
  const backupOutput = path.join(temp, "backup-output");
  fs.mkdirSync(liveSessions, { recursive: true });
  for (const file of fs.readdirSync(sessions)) fs.copyFileSync(path.join(sessions, file), path.join(liveSessions, file));
  const backupEnv = { ...process.env, HOME: home, TRAILKEEP_NO_NOTIFY: "1" };
  const first = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/Converted: 10/.test(first), "backup orchestrator did not convert the fixture", first);
  const stateDir = path.join(backupOutput, ".sync-state");
  const stateFiles = fs.readdirSync(stateDir).filter(name => name.endsWith(".size"));
  assert(stateFiles.length === 13, `expected 13 Codex state signatures, found ${stateFiles.length}`);
  for (const file of stateFiles) {
    const value = fs.readFileSync(path.join(stateDir, file), "utf8").trim();
    assert(value.endsWith(":codex-subagents-v2"), "Codex converter version was not committed");
  }
  const second = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/active: no changes/.test(second), "unchanged versioned Codex sources were reprocessed", second);
  for (const file of stateFiles) {
    const statePath = path.join(stateDir, file);
    const legacy = fs.readFileSync(statePath, "utf8").trim().split(":")[0];
    fs.writeFileSync(statePath, `${legacy}\n`);
  }
  const upgraded = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/13 new\/changed active/.test(upgraded), "legacy Codex state did not trigger one repair conversion", upgraded);
  const settled = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/active: no changes/.test(settled), "repair conversion did not settle", settled);

  const guardianOnlyId = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
  fs.writeFileSync(
    path.join(liveSessions, "rollout-guardian-only.jsonl"),
    guardianEvents(guardianOnlyId, "2026-07-16T10:14:00Z"),
  );
  const guardianOnly = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/Converted: 0/.test(guardianOnly) && /Ignored internal sessions: 1/.test(guardianOnly), "guardian-only batch was not ignored", guardianOnly);
  assert(guardianOnly.includes("internal approval-review transcript(s) ignored"), "guardian-only batch did not use the healthy ignored path", guardianOnly);
  assert(!/format may have changed/.test(guardianOnly), "guardian-only batch emitted a false format warning", guardianOnly);
  const guardianSettled = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/active: no changes/.test(guardianSettled), "guardian-only source signature was not committed", guardianSettled);

  const deferredOnlyId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  fs.writeFileSync(
    path.join(liveSessions, "rollout-deferred-only.jsonl"),
    markerlessChildEvents({
      id: deferredOnlyId,
      parentId: IDS.parent,
      agentPath: "/root/deferred_only",
      nickname: "Deferred only",
      start: "2026-07-16T10:11:00Z",
      completed: false,
    }),
  );
  const deferredOnly = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/Converted: 0/.test(deferredOnly) && /Deferred subagents: 1/.test(deferredOnly), "deferred-only conversion was not recognized", deferredOnly);
  assert(/safely deferred until child-authored turns appear/.test(deferredOnly), "deferred-only conversion did not use the healthy pending path", deferredOnly);
  assert(!/format may have changed/.test(deferredOnly), "deferred-only conversion emitted a false format warning", deferredOnly);
  const deferredSettled = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/active: no changes/.test(deferredSettled), "deferred-only source signature was not committed", deferredSettled);

  fs.writeFileSync(
    path.join(liveSessions, "rollout-completed-unreadable.jsonl"),
    markerlessChildEvents({
      id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
      parentId: IDS.parent,
      agentPath: "/root/completed_unreadable",
      nickname: "Completed unreadable",
      start: "2026-07-16T10:12:00Z",
      completed: true,
      readable: false,
    }),
  );
  fs.appendFileSync(
    path.join(liveSessions, "rollout-parent.jsonl"),
    `${message("assistant", "Parent changed alongside the unreadable child.", "2026-07-16T10:12:01Z", "final_answer")}\n`,
  );
  const completedUnreadable = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/Converted: 1/.test(completedUnreadable) && /Unreadable completed subagents: 1/.test(completedUnreadable), "mixed completed-unreadable batch was not detected", completedUnreadable);
  assert(/format may have changed/.test(completedUnreadable), "completed unreadable child did not preserve loud health detection", completedUnreadable);
  const completedRetry = run("/bin/bash", [BACKUP, "--only", "codex", backupOutput], { env: backupEnv });
  assert(/2 new\/changed active/.test(completedRetry), "mixed unreadable batch was incorrectly committed", completedRetry);

  console.log("PASS Codex subagent identity, safe boundaries, hierarchy, cache migration, ledger attribution, and repair conversion");
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
