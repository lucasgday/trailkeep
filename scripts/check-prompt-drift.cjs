#!/usr/bin/env node
/*
 * Verifies that the prompts embedded in viewer.html and docs/index.html stay in
 * sync with docs/prompts.md. The viewer is standalone/offline, so it embeds the
 * prompt copies instead of loading Markdown at runtime.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

function read(relPath) {
  return fs.readFileSync(path.join(ROOT, relPath), "utf8").replace(/\r\n/g, "\n");
}

function normalize(text) {
  return String(text || "").replace(/\r\n/g, "\n").trim();
}

function fencedPrompt(markdown, heading) {
  const headingRe = new RegExp(`^## ${heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$`, "m");
  const match = headingRe.exec(markdown);
  if (!match) throw new Error(`Missing heading: ${heading}`);
  const rest = markdown.slice(match.index + match[0].length);
  const fence = /```text\n([\s\S]*?)\n```/.exec(rest);
  if (!fence) throw new Error(`Missing text fence after heading: ${heading}`);
  return normalize(fence[1]);
}

function templateLiteralAfterReturn(source, functionName) {
  const fnIndex = source.indexOf(`function ${functionName}(`);
  if (fnIndex < 0) throw new Error(`Missing function ${functionName}`);
  const returnIndex = source.indexOf("return `", fnIndex);
  if (returnIndex < 0) throw new Error(`Missing template return in ${functionName}`);
  const start = returnIndex + "return `".length;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "`" && source[i - 1] !== "\\") {
      return normalize(source.slice(start, i));
    }
  }
  throw new Error(`Unterminated template return in ${functionName}`);
}

function canonicalizeManualPrompt(template) {
  return normalize(template)
    .replaceAll("${name}", "<project_name>")
    .replaceAll("${path}", "<project_path_or_virtual>")
    .replaceAll("${repo}", "<repo_url_or_none>")
    .replaceAll("${git}", "<branch_commit_dirty_or_none>")
    .replaceAll("${stack}", "<detected_stack_or_none>")
    .replaceAll('${projectStatusLabel(meta.status)||"-"}', "<active_inactive_gone_or_unknown>")
    .replaceAll("${sessions.length}", "<conversation_count>")
    .replaceAll("${activity}", "<ledger_activity>")
    .replaceAll("${recent}", "<recent_conversation_list>");
}

function firstDiff(expected, actual) {
  const a = expected.split("\n");
  const b = actual.split("\n");
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    if (a[i] !== b[i]) {
      return {
        line: i + 1,
        expected: a[i] ?? "<missing>",
        actual: b[i] ?? "<missing>",
      };
    }
  }
  return null;
}

function assertSame(label, expected, actual) {
  if (expected === actual) return;
  const diff = firstDiff(expected, actual);
  const detail = diff
    ? `line ${diff.line}\n  expected: ${diff.expected}\n  actual:   ${diff.actual}`
    : "content differs";
  throw new Error(`${label} drifted from docs/prompts.md at ${detail}`);
}

function htmlPrompts(relPath) {
  const html = read(relPath);
  return {
    setup: templateLiteralAfterReturn(html, "projectReviewSetupPrompt"),
    manual: canonicalizeManualPrompt(templateLiteralAfterReturn(html, "projectReviewPrompt")),
  };
}

function main() {
  const docs = read("docs/prompts.md");
  const canonical = {
    setup: fencedPrompt(docs, "Initial Setup"),
    manual: fencedPrompt(docs, "Manual Project Review"),
  };

  const viewer = htmlPrompts("viewer.html");
  const demo = htmlPrompts(path.join("docs", "index.html"));

  assertSame("viewer.html setup prompt", canonical.setup, viewer.setup);
  assertSame("docs/index.html setup prompt", canonical.setup, demo.setup);
  assertSame("viewer.html manual project prompt", canonical.manual, viewer.manual);
  assertSame("docs/index.html manual project prompt", canonical.manual, demo.manual);
  assertSame("viewer.html and docs/index.html setup prompts", viewer.setup, demo.setup);
  assertSame("viewer.html and docs/index.html manual prompts", viewer.manual, demo.manual);

  console.log("Prompt drift check passed.");
}

try {
  main();
} catch (err) {
  console.error(err && err.message ? err.message : err);
  process.exitCode = 1;
}
