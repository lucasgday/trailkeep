#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const ledgerScript = path.join(root, "converters", "extract_ledger.py");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-token-accounting-"));

function writeJsonl(file, rows) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

function writeMarkdown(outDir, project, id, source, assistant) {
  const dir = path.join(outDir, project);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, `${id}.md`),
    `# Token accounting fixture\n\n<!-- date: 2026-07-31T12:00:00Z | id: ${id} | project: ${project} | source: ${source} | archived: false -->\n\n### You\n\nMeasure this response.\n\n### ${assistant}\n\nMeasured.\n`,
  );
}

function runLedger(input, output, source, format) {
  execFileSync("python3", [ledgerScript, input, output, source, format], {
    cwd: root,
    stdio: "pipe",
  });
  return JSON.parse(fs.readFileSync(path.join(output, "_ledger.json"), "utf8")).sources[source];
}

function tokenUsage(input, output, cacheCreation, cacheRead) {
  return {
    input_tokens: input,
    output_tokens: output,
    cache_creation_input_tokens: cacheCreation,
    cache_read_input_tokens: cacheRead,
  };
}

function viewerAggregator(file) {
  const source = fs.readFileSync(file, "utf8");
  const start = source.indexOf("function aggregateLedger");
  const end = source.indexOf("function fmtNum", start);
  assert(start >= 0 && end > start, `aggregateLedger helper missing in ${file}`);
  return new Function(`${source.slice(start, end)}\nreturn aggregateLedger;`)();
}

try {
  const claudeId = "11111111-1111-4111-8111-111111111111";
  const claudeRaw = path.join(temp, "claude-raw");
  const claudeOut = path.join(temp, "markdown-claude");
  const claudeFile = path.join(claudeRaw, "-tmp-fixture-project", `${claudeId}.jsonl`);
  const repeated = tokenUsage(2, 100, 10, 1000);
  const claudeRows = [
    {
      type: "user", sessionId: claudeId, uuid: "user-1", parentUuid: null,
      cwd: "/tmp/fixture-project", timestamp: "2026-07-31T12:00:00Z",
      message: { role: "user", content: "Measure this response." },
    },
    ...[
      [{ type: "thinking", thinking: "Inspecting." }],
      [{ type: "text", text: "I will inspect it." }],
      [{ type: "tool_use", name: "Read", input: { file_path: "/tmp/a.txt" } }],
    ].map((content, index) => ({
      type: "assistant", sessionId: claudeId, uuid: `assistant-${index}`,
      parentUuid: "user-1", requestId: "request-1",
      cwd: "/tmp/fixture-project", timestamp: `2026-07-31T12:00:0${index + 1}Z`,
      message: { id: "message-1", role: "assistant", model: "claude-test", usage: repeated, content },
    })),
    {
      type: "assistant", sessionId: claudeId, uuid: "assistant-3", parentUuid: "assistant-2",
      requestId: "request-2", cwd: "/tmp/fixture-project", timestamp: "2026-07-31T12:00:05Z",
      message: {
        id: "message-2", role: "assistant", model: "claude-test",
        usage: tokenUsage(3, 50, 20, 2000), content: [{ type: "text", text: "Done." }],
      },
    },
  ];
  writeJsonl(claudeFile, claudeRows);
  writeMarkdown(claudeOut, "fixture-project", claudeId, "claude-code", "Claude");

  const claude = runLedger(claudeRaw, claudeOut, "claude-code", "claude");
  assert.deepStrictEqual(claude.tokens, {
    input: 5,
    output: 150,
    cache_creation: 30,
    cache_read: 3000,
  }, "Claude repeated content rows must count as two API responses");
  assert.deepStrictEqual(claude.tokens_by_model["claude-test"], claude.tokens);
  assert.strictEqual(claude.token_accounting_version, 2);
  assert.deepStrictEqual(claude.token_coverage, {
    normalized_runs: 1,
    legacy_runs: 0,
    unmeasured_runs: 0,
  });

  const codexId = "22222222-2222-4222-8222-222222222222";
  const codexRaw = path.join(temp, "codex-raw");
  const codexOut = path.join(temp, "markdown-codex");
  writeJsonl(path.join(codexRaw, "rollout-fixture.jsonl"), [
    {
      timestamp: "2026-07-31T12:10:00Z", type: "session_meta",
      payload: { id: codexId, timestamp: "2026-07-31T12:10:00Z", cwd: "/tmp/fixture-project", source: "cli" },
    },
    {
      timestamp: "2026-07-31T12:10:01Z", type: "response_item",
      payload: { type: "message", role: "user", content: [{ type: "input_text", text: "Measure this response." }] },
    },
    {
      timestamp: "2026-07-31T12:10:02Z", type: "event_msg",
      payload: {
        type: "token_count", model: "gpt-test",
        info: { total_token_usage: {
          input_tokens: 1000,
          cached_input_tokens: 800,
          output_tokens: 120,
          reasoning_output_tokens: 70,
          total_tokens: 1120,
        } },
      },
    },
    {
      timestamp: "2026-07-31T12:10:03Z", type: "response_item",
      payload: { type: "message", role: "assistant", content: [{ type: "output_text", text: "Measured." }] },
    },
  ]);
  writeMarkdown(codexOut, "fixture-project", codexId, "codex", "Codex");

  const codex = runLedger(codexRaw, codexOut, "codex", "codex");
  assert.deepStrictEqual(codex.tokens, {
    input: 200,
    output: 120,
    cache_creation: 0,
    cache_read: 800,
  }, "Codex reasoning tokens must not be added on top of output_tokens");
  assert.deepStrictEqual(codex.tokens_by_model["gpt-test"], codex.tokens);
  assert.strictEqual(codex.token_accounting_version, 2);

  const cachePath = path.join(claudeOut, "_ledger-cache.json");
  const legacyCache = JSON.parse(fs.readFileSync(cachePath, "utf8"));
  legacyCache.version = 9;
  for (const entry of Object.values(legacyCache.sessions || {})) {
    if (entry?.metrics) delete entry.metrics.token_accounting_version;
  }
  fs.writeFileSync(cachePath, JSON.stringify(legacyCache, null, 2));
  fs.rmSync(claudeFile);

  const carried = runLedger(claudeRaw, claudeOut, "claude-code", "claude");
  assert.deepStrictEqual(carried.tokens, {
    input: 0,
    output: 0,
    cache_creation: 0,
    cache_read: 0,
  }, "legacy token accounting must not mix into comparable totals");
  assert.deepStrictEqual(carried.legacy_tokens, claude.tokens, "legacy token evidence must remain preserved");
  assert.deepStrictEqual(carried.token_coverage, {
    normalized_runs: 0,
    legacy_runs: 1,
    unmeasured_runs: 0,
  });
  const migratedCache = JSON.parse(fs.readFileSync(cachePath, "utf8"));
  assert.strictEqual(migratedCache.version, 10);
  const carriedRaw = Object.values(migratedCache.sessions || {}).find((entry) =>
    entry?.metrics?.id === claudeId && entry.metrics.tokens?.cache_read === 3000);
  assert(carriedRaw, "legacy token evidence was removed from the cumulative cache");

  const aggregateFixture = { sources: {
    normalized: {
      token_accounting_version: 2,
      totals: { sessions: 1 },
      tokens: { input: 5, output: 7, cache_creation: 11, cache_read: 13 },
      token_coverage: { normalized_runs: 1, legacy_runs: 0, unmeasured_runs: 0 },
      tokens_by_model: { "model-new": { input: 5, output: 7, cache_creation: 11, cache_read: 13 } },
    },
    legacy: {
      totals: { sessions: 2 },
      tokens: { input: 100, output: 200, cache_creation: 300, cache_read: 400 },
      tokens_by_model: { "model-old": { input: 100, output: 200, cache_creation: 300, cache_read: 400 } },
    },
  } };
  const viewerResult = viewerAggregator(path.join(root, "viewer.html"))(aggregateFixture);
  const demoResult = viewerAggregator(path.join(root, "docs", "index.html"))(aggregateFixture);
  assert.deepStrictEqual(viewerResult.tokens, aggregateFixture.sources.normalized.tokens);
  assert.deepStrictEqual(viewerResult.tokens_by_model, aggregateFixture.sources.normalized.tokens_by_model);
  assert.deepStrictEqual(viewerResult.legacy_tokens, aggregateFixture.sources.legacy.tokens);
  assert.deepStrictEqual(viewerResult.token_coverage, {
    normalized_runs: 1,
    legacy_runs: 2,
    unmeasured_runs: 0,
  });
  assert.deepStrictEqual(demoResult, viewerResult, "viewer and demo token aggregation drifted");

  console.log("ledger token accounting fixtures: ok");
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
