#!/usr/bin/env python3
"""Check local project repo freshness for a trailkeep review run.

This script belongs to the optional coding-agent review layer, not the local
backup. It may run `git fetch` to update remote-tracking refs, but it never runs
`git pull` and never modifies the working tree.

It writes `_review_repo_sync.json` at the backup root and exits 0 even when a
particular repo cannot be checked; per-project uncertainty is recorded in the
sidecar so the automation can mark the review accordingly.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys


PLAN_FILE = "_review_run_plan.json"
EFFECTIVE_PLAN_FILE = "_review_effective_plan.json"
PROJECTS_FILE = "_projects.json"
OUTPUT_FILE = "_review_repo_sync.json"


def now():
    return datetime.datetime.now().astimezone().isoformat()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sidecar_path(backup_dir, name):
    return os.path.join(backup_dir, name)


def sanitize_error(text):
    text = str(text or "").strip().replace("\n", " ")
    text = re.sub(r"(https?://)[^/@\s]+@", r"\1<redacted>@", text)
    text = re.sub(r"\s+", " ", text)
    return text[:500]


def git(cwd, args, timeout):
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": sanitize_error(proc.stderr),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "code": None,
            "stdout": "",
            "stderr": f"git {' '.join(args)} timed out after {timeout}s",
            "timed_out": True,
        }
    except Exception as exc:
        return {
            "ok": False,
            "code": None,
            "stdout": "",
            "stderr": sanitize_error(str(exc)),
            "timed_out": False,
        }


def load_plan(backup_dir):
    effective = load_json(sidecar_path(backup_dir, EFFECTIVE_PLAN_FILE), None)
    if isinstance(effective, dict):
        return effective
    plan = load_json(sidecar_path(backup_dir, PLAN_FILE), {})
    return plan if isinstance(plan, dict) else {}


def planned_project_names(plan):
    names = []
    for project in plan.get("projects") or []:
        if isinstance(project, dict) and project.get("name"):
            names.append(str(project["name"]))
    return names


def project_metadata(backup_dir, plan):
    projects_doc = load_json(sidecar_path(backup_dir, PROJECTS_FILE), {})
    projects = projects_doc.get("projects") if isinstance(projects_doc, dict) else {}
    if not isinstance(projects, dict):
        projects = {}
    merged = {str(name): dict(meta) for name, meta in projects.items() if isinstance(meta, dict)}
    for project in plan.get("projects") or []:
        if not isinstance(project, dict) or not project.get("name"):
            continue
        name = str(project["name"])
        meta = merged.setdefault(name, {})
        if project.get("path") and not meta.get("path"):
            meta["path"] = project.get("path")
        if project.get("status") and not meta.get("status"):
            meta["status"] = project.get("status")
    return merged


def project_names_to_check(plan, metadata):
    planned = planned_project_names(plan)
    return planned if planned else sorted(metadata)


def inside_git_repo(path, timeout):
    result = git(path, ["rev-parse", "--is-inside-work-tree"], timeout)
    return result["ok"] and result["stdout"].strip() == "true"


def git_value(path, args, timeout, default=""):
    result = git(path, args, timeout)
    return result["stdout"].strip() if result["ok"] else default


def ahead_behind(path, timeout):
    result = git(path, ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"], timeout)
    if not result["ok"]:
        return None, None, result["stderr"] or "could not compare HEAD with upstream"
    parts = result["stdout"].split()
    if len(parts) != 2:
        return None, None, f"unexpected ahead/behind output: {result['stdout']}"
    try:
        return int(parts[0]), int(parts[1]), ""
    except ValueError:
        return None, None, f"unexpected ahead/behind output: {result['stdout']}"


def remote_commit_subjects(path, timeout, limit):
    if limit <= 0:
        return []
    result = git(path, ["log", f"--max-count={limit}", "--format=%h %s", "HEAD..@{upstream}"], timeout)
    if not result["ok"]:
        return []
    return [line for line in result["stdout"].splitlines() if line.strip()]


def check_project(name, meta, args):
    checked_at = now()
    path = meta.get("path") or ""
    row = {
        "project": name,
        "path": path,
        "checked_at": checked_at,
        "repo_sync_checked_at": checked_at,
        "is_git": False,
        "fetch_attempted": False,
        "fetch_ok": False,
        "sync_status": "skipped",
        "sync_uncertain": False,
        "repo_may_be_stale": False,
        "needs_deep_review": False,
        "local_ahead": None,
        "local_behind": None,
        "remote_ahead": None,
        "remote_behind": None,
        "errors": [],
    }
    if meta.get("virtual"):
        row["sync_status"] = "virtual_project"
        return row
    if not path:
        row["sync_status"] = "missing_path"
        return row
    if not os.path.isdir(path):
        row["sync_status"] = "missing_path"
        row["errors"].append("project path does not exist")
        return row
    if not inside_git_repo(path, args.timeout_seconds):
        row["sync_status"] = "not_git"
        return row

    row["is_git"] = True
    row["head"] = git_value(path, ["rev-parse", "--short", "HEAD"], args.timeout_seconds)
    row["branch"] = git_value(path, ["rev-parse", "--abbrev-ref", "HEAD"], args.timeout_seconds)
    row["upstream"] = git_value(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], args.timeout_seconds)
    remote = git_value(path, ["config", f"branch.{row['branch']}.remote"], args.timeout_seconds) if row["branch"] else ""
    row["remote"] = remote
    if not row["upstream"] or not remote:
        row["sync_status"] = "no_upstream"
        row["sync_uncertain"] = True
        return row

    if not args.no_fetch:
        row["fetch_attempted"] = True
        fetch = git(path, ["fetch", "--quiet", "--prune", remote], args.timeout_seconds)
        row["fetch_ok"] = fetch["ok"]
        if not fetch["ok"]:
            row["sync_status"] = "fetch_failed"
            row["sync_uncertain"] = True
            row["errors"].append(fetch["stderr"] or "git fetch failed")
            return row

    local_ahead, remote_ahead, error = ahead_behind(path, args.timeout_seconds)
    if error:
        row["sync_status"] = "compare_failed"
        row["sync_uncertain"] = True
        row["errors"].append(error)
        return row

    row["local_ahead"] = local_ahead
    row["local_behind"] = remote_ahead
    row["remote_ahead"] = remote_ahead
    row["remote_behind"] = local_ahead
    row["repo_may_be_stale"] = remote_ahead > 0
    row["needs_deep_review"] = row["repo_may_be_stale"]
    row["remote_commit_subjects"] = remote_commit_subjects(path, args.timeout_seconds, args.max_remote_commits)
    if local_ahead and remote_ahead:
        row["sync_status"] = "diverged"
    elif remote_ahead:
        row["sync_status"] = "behind_remote"
    elif local_ahead:
        row["sync_status"] = "ahead_remote"
    else:
        row["sync_status"] = "synced"
    return row


def build_summary(rows):
    values = list(rows.values())
    return {
        "projects_checked": len(values),
        "git_repos": sum(1 for row in values if row.get("is_git")),
        "fetch_attempted": sum(1 for row in values if row.get("fetch_attempted")),
        "repo_may_be_stale": sorted(row["project"] for row in values if row.get("repo_may_be_stale")),
        "sync_uncertain": sorted(row["project"] for row in values if row.get("sync_uncertain")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--no-fetch", action="store_true", help="Do not contact remotes; compare against local remote-tracking refs only.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-remote-commits", type=int, default=8)
    args = parser.parse_args()
    backup_dir = os.path.abspath(args.backup_dir)
    if not os.path.isdir(backup_dir):
        print(json.dumps({"status": "failed", "errors": [f"backup dir does not exist: {backup_dir}"]}))
        return 1

    plan = load_plan(backup_dir)
    metadata = project_metadata(backup_dir, plan)
    names = project_names_to_check(plan, metadata)
    rows = {}
    for name in names:
        rows[name] = check_project(name, metadata.get(name) or {}, args)

    doc = {
        "version": 1,
        "checked_at": now(),
        "source": "trailkeep-project-review/check_repo_sync.py",
        "network_attempted": any(row.get("fetch_attempted") for row in rows.values()),
        "fetch_enabled": not args.no_fetch,
        "projects": rows,
        "summary": build_summary(rows),
        "notes": [
            "This sidecar is written only by the optional coding-agent review layer.",
            "git fetch may update remote-tracking refs, but this script never runs git pull and never modifies the working tree.",
        ],
    }
    write_json(sidecar_path(backup_dir, OUTPUT_FILE), doc)
    print(json.dumps({"status": "ok", "output": OUTPUT_FILE, "summary": doc["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
