#!/usr/bin/env node
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..");
const fixtureRoot = path.join(
  repoRoot,
  "skills",
  "trailkeep-project-review",
  "fixtures",
  "generated-review-evals",
);
const baseFixture = path.join(fixtureRoot, "valid-basic");
const reportName = "_review_generated_eval_report.json";

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function mergeJson(target, patch) {
  if (!isPlainObject(target) || !isPlainObject(patch)) return patch;
  const merged = { ...target };
  for (const [key, value] of Object.entries(patch)) {
    merged[key] = isPlainObject(value) && isPlainObject(merged[key])
      ? mergeJson(merged[key], value)
      : value;
  }
  return merged;
}

function deletePath(target, segments) {
  if (!Array.isArray(segments) || segments.length === 0) return;
  let cursor = target;
  for (const segment of segments.slice(0, -1)) {
    if (!isPlainObject(cursor) && !Array.isArray(cursor)) return;
    cursor = cursor[segment];
    if (cursor == null) return;
  }
  if (isPlainObject(cursor) || Array.isArray(cursor)) {
    delete cursor[segments[segments.length - 1]];
  }
}

function applyFixtureConfig(workDir, config) {
  for (const [relativePath, patch] of Object.entries(config.overrides || {})) {
    const jsonPath = path.join(workDir, relativePath);
    const current = fs.existsSync(jsonPath) ? readJson(jsonPath) : {};
    writeJson(jsonPath, mergeJson(current, patch));
  }

  for (const [relativePath, paths] of Object.entries(config.deletePaths || {})) {
    const jsonPath = path.join(workDir, relativePath);
    const current = readJson(jsonPath);
    for (const segments of paths) {
      deletePath(current, segments);
    }
    writeJson(jsonPath, current);
  }
}

function failingCheckNames(report) {
  return (report.checks || [])
    .filter((check) => check.status === "fail")
    .map((check) => check.name);
}

function runFixture(name) {
  const fixtureDir = path.join(fixtureRoot, name);
  const configPath = path.join(fixtureDir, "fixture.json");
  const config = readJson(configPath);
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-generated-evals-"));
  const workDir = path.join(tmpRoot, name);
  fs.cpSync(baseFixture, workDir, { recursive: true });
  applyFixtureConfig(workDir, config);

  const child = spawnSync(
    "python3",
    ["converters/eval_generated_reviews.py", workDir],
    { cwd: repoRoot, encoding: "utf8" },
  );
  const reportPath = path.join(workDir, reportName);
  const report = fs.existsSync(reportPath) ? readJson(reportPath) : null;
  const actualExitCode = child.status == null ? 1 : child.status;
  const expectedExitCode = Number(config.expectedExitCode || 0);
  const expectedStatus = config.expectedStatus || (expectedExitCode === 0 ? "pass" : "fail");
  const failedChecks = report ? failingCheckNames(report) : [];
  const missingExpectedChecks = (config.expectedFailureChecks || []).filter(
    (checkName) => !failedChecks.includes(checkName),
  );

  const mismatches = [];
  if (actualExitCode !== expectedExitCode) {
    mismatches.push(`expected exit ${expectedExitCode}, got ${actualExitCode}`);
  }
  if (!report) {
    mismatches.push(`missing ${reportName}`);
  } else if (report.status !== expectedStatus) {
    mismatches.push(`expected report status ${expectedStatus}, got ${report.status}`);
  }
  if (missingExpectedChecks.length) {
    mismatches.push(`missing expected failing check(s): ${missingExpectedChecks.join(", ")}`);
  }

  const keep = process.env.KEEP_TRAILKEEP_EVAL_FIXTURES === "1";
  if (!keep) {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }

  return {
    name,
    description: config.description,
    ok: mismatches.length === 0,
    mismatches,
    failedChecks,
    stdout: child.stdout.trim(),
    stderr: child.stderr.trim(),
    workDir: keep ? workDir : null,
  };
}

function main() {
  if (!fs.existsSync(baseFixture)) {
    console.error(`Missing base fixture: ${baseFixture}`);
    process.exit(1);
  }

  const fixtureNames = fs
    .readdirSync(fixtureRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort((a, b) => (a === "valid-basic" ? -1 : b === "valid-basic" ? 1 : a.localeCompare(b)));

  let failed = 0;
  for (const fixtureName of fixtureNames) {
    const result = runFixture(fixtureName);
    const marker = result.ok ? "PASS" : "FAIL";
    const failedSuffix = result.failedChecks.length
      ? ` (${result.failedChecks.join(", ")})`
      : "";
    console.log(`${marker} ${fixtureName}${failedSuffix}`);
    if (!result.ok) {
      failed += 1;
      for (const mismatch of result.mismatches) {
        console.error(`  - ${mismatch}`);
      }
      if (result.stdout) console.error(`  stdout: ${result.stdout}`);
      if (result.stderr) console.error(`  stderr: ${result.stderr}`);
      if (result.workDir) console.error(`  fixture copy: ${result.workDir}`);
    }
  }

  if (failed) {
    console.error(`${failed} generated-review eval fixture(s) failed.`);
    process.exit(1);
  }
  console.log(`${fixtureNames.length} generated-review eval fixture(s) passed.`);
}

main();
