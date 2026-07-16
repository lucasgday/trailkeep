#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const root = path.resolve(__dirname, "..");
const script = path.join(root, "update-backup.sh");
const installer = path.join(root, "install-auto.command");

function assert(condition, message, output = "") {
  if (condition) return;
  throw new Error(`${message}${output ? `\n${output}` : ""}`);
}

function runBackup(home, output, extraArgs = [], scriptPath = script) {
  const args = [scriptPath, "--only", "claude", ...extraArgs];
  if (output) args.push(output);
  const result = spawnSync("/bin/bash", args, {
    cwd: root,
    env: { ...process.env, HOME: home },
    encoding: "utf8",
  });
  const combined = `${result.stdout || ""}${result.stderr || ""}`;
  assert(result.status === 0, `backup exited ${result.status}`, combined);
  return combined;
}

function writeSource(home, name, content) {
  const dir = path.join(home, ".claude", "projects", "demo");
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, name), content);
}

function makeIsolatedApp(temp, name, withLegacyBackups = false) {
  const app = path.join(temp, name);
  fs.mkdirSync(app, { recursive: true });
  fs.symlinkSync(script, path.join(app, "update-backup.sh"));
  fs.symlinkSync(path.join(root, "converters"), path.join(app, "converters"), "dir");
  if (withLegacyBackups) fs.mkdirSync(path.join(app, "markdown-claude"));
  return app;
}

function stateFiles(output) {
  const dir = path.join(output, ".sync-state");
  return fs.existsSync(dir) ? fs.readdirSync(dir).filter(name => name.endsWith(".size")) : [];
}

const temp = fs.mkdtempSync(path.join(os.tmpdir(), "trailkeep-backup-retry-"));
try {
  // Any test that omits OUTPUT_DIR must run beside an isolated script symlink.
  // Otherwise legacy-path detection could discover and mutate a maintainer's real
  // repo-local backups while the test is only trying to exercise defaults.
  const cleanApp = makeIsolatedApp(temp, "clean-app");
  const cleanScript = path.join(cleanApp, "update-backup.sh");

  const invalidHome = path.join(temp, "invalid-home");
  const invalidOutput = path.join(temp, "invalid-output");
  fs.mkdirSync(invalidOutput, { recursive: true });
  writeSource(invalidHome, "invalid.jsonl", "not valid jsonl\n");

  const invalidFirst = runBackup(invalidHome, invalidOutput);
  const invalidSecond = runBackup(invalidHome, invalidOutput);
  assert(/1 new\/changed sessions/.test(invalidFirst), "first invalid run did not detect the source", invalidFirst);
  assert(/converted 0 sessions/.test(invalidFirst), "first invalid run did not report conversion failure", invalidFirst);
  assert(/1 new\/changed sessions/.test(invalidSecond), "failed conversion was incorrectly marked processed", invalidSecond);
  assert(/converted 0 sessions/.test(invalidSecond), "second invalid run did not retry and warn", invalidSecond);
  assert(stateFiles(invalidOutput).length === 0, "failed conversion wrote processed-state files");

  const validHome = path.join(temp, "valid-home");
  const validOutput = path.join(temp, "valid-output");
  fs.mkdirSync(validOutput, { recursive: true });
  writeSource(validHome, "session-1.jsonl", [
    JSON.stringify({ type: "user", sessionId: "session-1", timestamp: "2026-07-10T10:00:00Z", cwd: "/tmp/demo", message: { role: "user", content: "Keep this conversation" } }),
    JSON.stringify({ type: "assistant", sessionId: "session-1", timestamp: "2026-07-10T10:00:01Z", cwd: "/tmp/demo", message: { role: "assistant", content: "It is backed up" } }),
    "",
  ].join("\n"));

  const validFirst = runBackup(validHome, validOutput);
  const validSecond = runBackup(validHome, validOutput);
  assert(/Converted: 1/.test(validFirst), "valid source was not converted", validFirst);
  assert(/no changes/.test(validSecond), "successful conversion was not committed", validSecond);
  assert(stateFiles(validOutput).length === 1, "successful conversion did not write exactly one processed-state file");

  const defaultHome = path.join(temp, "default-home");
  writeSource(defaultHome, "session-default.jsonl", [
    JSON.stringify({ type: "user", sessionId: "session-default", timestamp: "2026-07-10T11:00:00Z", cwd: "/tmp/default", message: { role: "user", content: "Use the default folder" } }),
    "",
  ].join("\n"));
  const defaultRun = runBackup(defaultHome, null, [], cleanScript);
  const defaultOutput = path.join(defaultHome, "trailkeep-backups");
  assert(defaultRun.includes(`Base: ${defaultOutput}`), "default backup_dir was not reported", defaultRun);
  assert(fs.existsSync(path.join(defaultOutput, "markdown-claude")), "default backup_dir was not created");

  const legacyHome = path.join(temp, "legacy-home");
  const legacyApp = makeIsolatedApp(temp, "legacy-app", true);
  writeSource(legacyHome, "session-legacy.jsonl", [
    JSON.stringify({ type: "user", sessionId: "session-legacy", timestamp: "2026-07-10T11:30:00Z", cwd: "/tmp/legacy", message: { role: "user", content: "Keep the legacy folder" } }),
    "",
  ].join("\n"));
  const legacyRun = runBackup(legacyHome, null, [], path.join(legacyApp, "update-backup.sh"));
  assert(legacyRun.includes(`Base: ${legacyApp}`), "existing repo-local backup_dir was not preserved", legacyRun);
  assert(legacyRun.includes("keeping their legacy location"), "legacy backup_dir was not reported", legacyRun);

  const rememberedHome = path.join(temp, "remembered-home");
  const rememberedOutput = path.join(temp, "remembered-output");
  writeSource(rememberedHome, "session-remembered.jsonl", [
    JSON.stringify({ type: "user", sessionId: "session-remembered", timestamp: "2026-07-10T12:00:00Z", cwd: "/tmp/remembered", message: { role: "user", content: "Use the remembered folder" } }),
    "",
  ].join("\n"));
  const configDir = path.join(rememberedHome, ".config", "trailkeep");
  fs.mkdirSync(configDir, { recursive: true });
  fs.writeFileSync(path.join(configDir, "backup_dir"), `${rememberedOutput}\n`);
  const rememberedRun = runBackup(rememberedHome, null, [], cleanScript);
  assert(rememberedRun.includes(`Base: ${rememberedOutput}`), "remembered backup_dir was not used", rememberedRun);
  assert(fs.existsSync(path.join(rememberedOutput, "markdown-claude")), "remembered backup_dir was not created");

  const dryHome = path.join(temp, "dry-home");
  writeSource(dryHome, "session-dry.jsonl", [
    JSON.stringify({ type: "user", sessionId: "session-dry", timestamp: "2026-07-10T13:00:00Z", cwd: "/tmp/dry", message: { role: "user", content: "Do not write in dry run" } }),
    "",
  ].join("\n"));
  runBackup(dryHome, null, ["--dry-run"], cleanScript);
  assert(!fs.existsSync(path.join(dryHome, "trailkeep-backups")), "dry-run created the default backup_dir");

  const installHome = path.join(temp, "install-home");
  const installOutput = path.join(temp, "install output");
  const fakeBin = path.join(temp, "fake-bin");
  const cronCapture = path.join(temp, "installed-crontab");
  fs.mkdirSync(fakeBin, { recursive: true });
  fs.writeFileSync(path.join(fakeBin, "uname"), "#!/bin/sh\necho Linux\n");
  fs.writeFileSync(path.join(fakeBin, "crontab"), "#!/bin/sh\nif [ \"$1\" = \"-l\" ]; then [ -f \"$CRON_CAPTURE\" ] && cat \"$CRON_CAPTURE\"; exit 0; fi\ncat > \"$CRON_CAPTURE\"\n");
  fs.chmodSync(path.join(fakeBin, "uname"), 0o755);
  fs.chmodSync(path.join(fakeBin, "crontab"), 0o755);
  const installResult = spawnSync("/bin/bash", [installer, "7:30", installOutput], {
    cwd: root,
    env: { ...process.env, HOME: installHome, PATH: `${fakeBin}:${process.env.PATH}`, CRON_CAPTURE: cronCapture },
    encoding: "utf8",
  });
  const installLog = `${installResult.stdout || ""}${installResult.stderr || ""}`;
  assert(installResult.status === 0, `isolated installer exited ${installResult.status}`, installLog);
  const rememberedPath = path.join(installHome, ".config", "trailkeep", "backup_dir");
  assert(fs.readFileSync(rememberedPath, "utf8").trim() === installOutput, "installer did not remember backup_dir", installLog);
  assert(fs.readFileSync(cronCapture, "utf8").includes(installOutput), "scheduled command did not use remembered backup_dir", installLog);
  assert(installLog.includes(`Backup folder: ${installOutput}`), "installer did not report backup_dir", installLog);

  console.log("PASS backup retry transaction, backup_dir defaults, and installer memory");
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
