#!/usr/bin/env node
/*
 * Verifies that the optional coding-agent automation instructions preserve
 * macOS power-management state. A stale caffeinate process can leave the user's
 * machine with sleep/display sleep disabled long after a review run ends.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");

function read(relPath) {
  return fs.readFileSync(path.join(ROOT, relPath), "utf8");
}

function requireText(relPath, needles) {
  const text = read(relPath).replace(/`/g, "").replace(/\s+/g, " ");
  const missing = needles.filter((needle) => !text.includes(needle));
  if (missing.length) {
    throw new Error(`${relPath} is missing automation power guardrail text: ${missing.join(", ")}`);
  }
}

function main() {
  const common = [
    "caffeinate",
    "Do not start caffeinate",
    "change pmset",
    "disable the screen saver",
  ];

  requireText("docs/generative-layer.md", common);
  requireText("skills/trailkeep-project-review/SKILL.md", common);
  requireText("docs/prompts.md", common);
  requireText("viewer.html", common);
  requireText(path.join("docs", "index.html"), common);

  console.log("Automation guardrail check passed.");
}

try {
  main();
} catch (err) {
  console.error(err && err.message ? err.message : err);
  process.exitCode = 1;
}
