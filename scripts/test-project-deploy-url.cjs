#!/usr/bin/env node
"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const repo = path.resolve(__dirname, "..");
const extractor = path.join(repo, "converters", "extract_projects.py");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-project-deploy-"));

function claudeRow(type, cwd, timestamp, content) {
  return {
    type,
    cwd,
    timestamp,
    sessionId: `${path.basename(cwd)}-session`,
    message: { role: type, content },
  };
}

function codexEvent(type, payload, timestamp) {
  return JSON.stringify({ type, payload, timestamp });
}

function codexMessage(role, text, timestamp) {
  return codexEvent("response_item", {
    type: "message",
    role,
    content: [{ type: role === "assistant" ? "output_text" : "input_text", text }],
  }, timestamp);
}

function projectsFor(out) {
  return JSON.parse(fs.readFileSync(path.join(out, "_projects.json"), "utf8")).projects;
}

try {
  const claudeRoot = path.join(temp, "claude");
  const codexRoot = path.join(temp, "codex");
  const out = path.join(temp, "backup");
  const productionPath = path.join(temp, "production-site");
  const previewPath = path.join(temp, "preview-only");
  const codexPath = path.join(temp, "codex-site");
  const tldPath = path.join(temp, "tld-site");
  for (const dir of [claudeRoot, codexRoot, productionPath, previewPath, codexPath, tldPath]) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(
    path.join(productionPath, "README.md"),
    "Production URL: https://old.production-site.example.com\n",
  );
  fs.writeFileSync(
    path.join(previewPath, "README.md"),
    "Preview URL: https://preview-only-preview.example.com\n",
  );
  fs.writeFileSync(
    path.join(tldPath, "README.md"),
    "Production URL: https://tld-site.dev\n",
  );

  const productionSession = [
    claudeRow("user", productionPath, "2026-08-18T09:00:00Z", "Ship the site."),
    claudeRow("assistant", productionPath, "2026-08-18T09:01:00Z", [
      { type: "tool_use", name: "Bash", input: { command: "vercel --prod" } },
    ]),
    claudeRow("user", productionPath, "2026-08-18T09:01:01Z", [
      { type: "tool_result", content: "Production: https://old.production-site.example.com" },
    ]),
    claudeRow("assistant", productionPath, "2026-08-18T10:00:00Z", "Production deployment updated: https://new.production-site.example.com"),
    claudeRow("assistant", productionPath, "2026-08-18T11:00:00Z", "Preview deployment: https://production-site-git-feature.vercel.app"),
  ].map((row) => JSON.stringify(row)).join("\n") + "\n";
  fs.writeFileSync(path.join(claudeRoot, "production.jsonl"), productionSession);

  const previewSession = [
    claudeRow("user", previewPath, "2026-08-18T09:00:00Z", "Create a preview."),
    claudeRow("assistant", previewPath, "2026-08-18T09:01:00Z", "Preview URL: https://preview-only-git-feature.vercel.app"),
  ].map((row) => JSON.stringify(row)).join("\n") + "\n";
  fs.writeFileSync(path.join(claudeRoot, "preview.jsonl"), previewSession);

  const tldSession = [
    claudeRow("user", tldPath, "2026-08-18T09:00:00Z", "Inspect the site."),
    claudeRow("assistant", tldPath, "2026-08-18T09:01:00Z", "The site looks healthy."),
  ].map((row) => JSON.stringify(row)).join("\n") + "\n";
  fs.writeFileSync(path.join(claudeRoot, "tld.jsonl"), tldSession);

  const codexSession = [
    codexEvent("session_meta", {
      id: "codex-session",
      cwd: codexPath,
      source: "vscode",
    }, "2026-08-18T08:00:00Z"),
    codexMessage("user", "Deploy the site.", "2026-08-18T08:01:00Z"),
    codexEvent("response_item", {
      type: "custom_tool_call",
      name: "exec",
      input: "vercel --prod",
    }, "2026-08-18T08:02:00Z"),
    codexEvent("response_item", {
      type: "custom_tool_call_output",
      output: "Production: https://codex-site.example.com",
    }, "2026-08-18T08:03:00Z"),
    codexEvent("response_item", {
      type: "custom_tool_call_output",
      output: "Preview: https://codex-site-git-feature.vercel.app",
    }, "2026-08-18T09:00:00Z"),
  ].join("\n") + "\n";
  fs.writeFileSync(path.join(codexRoot, "rollout-codex.jsonl"), codexSession);

  const replayedParent = [
    codexEvent("session_meta", {
      id: "child-session",
      cwd: codexPath,
      source: { subagent: { thread_spawn: { parent_thread_id: "parent-session" } } },
    }, "2026-08-18T12:00:00Z"),
    codexEvent("session_meta", {
      id: "parent-session",
      cwd: codexPath,
      source: "vscode",
    }, "2026-08-18T11:00:00Z"),
    codexMessage("assistant", "Production: https://inherited-parent.example.com", "2026-08-18T12:01:00Z"),
    codexEvent("inter_agent_communication_metadata", {}, "2026-08-18T12:02:00Z"),
  ].join("\n") + "\n";
  fs.writeFileSync(path.join(codexRoot, "rollout-replayed-parent.jsonl"), replayedParent);

  execFileSync(
    "python3",
    [extractor, out, `claude=${claudeRoot}`, `codex=${codexRoot}`],
    { cwd: repo, stdio: "pipe" },
  );
  const projects = projectsFor(out);

  assert.strictEqual(
    projects["production-site"].deploy_url,
    "https://new.production-site.example.com",
    "the newest production URL from a conversation should win",
  );
  assert.strictEqual(
    projects["preview-only"].deploy_url,
    null,
    "preview-only conversation and README URLs must be ignored",
  );
  assert.strictEqual(
    projects["codex-site"].deploy_url,
    "https://codex-site.example.com",
    "Codex tool output should provide the production URL",
  );
  assert.strictEqual(
    projects["tld-site"].deploy_url,
    "https://tld-site.dev",
    "a production .dev domain must not be mistaken for a development URL",
  );

  console.log("Project production deploy URL detection: ok");
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
