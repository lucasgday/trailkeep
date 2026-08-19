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
const projectsExtractor = path.join(repo, "converters", "extract_projects.py");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-claude-project-"));
const sessionId = "11111111-2222-4333-8444-555555555555";

function writeSession(file, cwd) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const rows = [
    {
      type: "user",
      cwd,
      timestamp: "2026-07-30T12:00:00.000Z",
      sessionId,
      message: { role: "user", content: "Fix the billing conversion." },
    },
    {
      type: "assistant",
      cwd,
      timestamp: "2026-07-30T12:00:01.000Z",
      sessionId,
      message: {
        role: "assistant",
        model: "claude-test",
        usage: { input_tokens: 10, output_tokens: 5 },
        content: [{ type: "text", text: "I will inspect it." }],
      },
    },
  ];
  fs.writeFileSync(file, rows.map((row) => JSON.stringify(row)).join("\n") + "\n");
}

function projectRows(outDir, source) {
  const doc = JSON.parse(fs.readFileSync(path.join(outDir, "_ledger.json"), "utf8"));
  return doc.sources[source].projects;
}

function writeInternalSession(file, cwd) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const rows = [
    {
      type: "user",
      cwd,
      timestamp: "2026-07-30T13:00:00.000Z",
      sessionId: "66666666-7777-4888-8999-000000000000",
      message: { role: "user", content: "<local-command-caveat>Generated local UI wrapper.</local-command-caveat>" },
    },
    {
      type: "user",
      cwd,
      timestamp: "2026-07-30T13:00:01.000Z",
      sessionId: "66666666-7777-4888-8999-000000000000",
      message: { role: "user", content: "<local-command-stdout>Settings saved.</local-command-stdout>" },
    },
  ];
  fs.writeFileSync(file, rows.map((row) => JSON.stringify(row)).join("\n") + "\n");
}

try {
  const claudeRoot = path.join(tmp, "claude");
  const claudeOut = path.join(tmp, "markdown-claude");
  const encodedProject = path.join(
    claudeRoot,
    "-Users-test-code-CascadeProjects-facturante-conversion",
  );
  writeSession(
    path.join(encodedProject, `${sessionId}.jsonl`),
    "/Users/test/code/CascadeProjects/facturante-conversion",
  );

  execFileSync(
    "python3",
    [converter, claudeRoot, claudeOut, "claude-code", path.join(tmp, "missing-history.jsonl")],
    { cwd: repo, stdio: "pipe" },
  );
  const projectDir = path.join(claudeOut, "facturante-conversion");
  const markdown = fs.readFileSync(
    path.join(projectDir, fs.readdirSync(projectDir).find((name) => name.endsWith(".md"))),
    "utf8",
  );
  assert(markdown.includes("project: facturante-conversion"));
  assert(markdown.includes("format_version: 3"));
  assert(!fs.existsSync(path.join(claudeOut, "conversion")));

  execFileSync(
    "python3",
    [ledger, claudeRoot, claudeOut, "claude-code", "claude"],
    { cwd: repo, stdio: "pipe" },
  );
  assert(projectRows(claudeOut, "claude-code").some((row) =>
    row.project === "facturante-conversion" && row.sessions === 1));
  assert(!projectRows(claudeOut, "claude-code").some((row) => row.project === "conversion"));

  writeInternalSession(
    path.join(encodedProject, "66666666-7777-4888-8999-000000000000.jsonl"),
    "/Users/test/code/CascadeProjects/facturante-conversion",
  );
  execFileSync(
    "python3",
    [projectsExtractor, claudeOut, `claude=${claudeRoot}`],
    { cwd: repo, stdio: "pipe" },
  );
  const projects = JSON.parse(fs.readFileSync(path.join(claudeOut, "_projects.json"), "utf8"));
  assert.strictEqual(
    projects.projects["facturante-conversion"].last_activity,
    "2026-07-30T12:00:01.000Z",
    "project activity should use the final visible message and ignore later local-command sessions",
  );

  const coworkRoot = path.join(tmp, "cowork");
  const coworkOut = path.join(tmp, "markdown-cowork");
  writeSession(
    path.join(coworkRoot, "cowork", `${sessionId}.jsonl`),
    "/sessions/throwaway-sandbox",
  );
  execFileSync(
    "python3",
    [converter, coworkRoot, coworkOut, "cowork", path.join(tmp, "missing-history.jsonl")],
    { cwd: repo, stdio: "pipe" },
  );
  assert(fs.existsSync(path.join(coworkOut, "cowork")));

  execFileSync(
    "python3",
    [ledger, coworkRoot, coworkOut, "cowork", "claude"],
    { cwd: repo, stdio: "pipe" },
  );
  assert(projectRows(coworkOut, "cowork").some((row) =>
    row.project === "cowork" && row.sessions === 1));

  console.log("Claude hyphenated project attribution: ok");
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}
