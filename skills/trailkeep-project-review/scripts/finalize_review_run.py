#!/usr/bin/env python3
"""Finalize a trailkeep generated review run.

Runs generated-output evals, appends `_review_update_log.json`, reruns evals so
the log is validated, and exits nonzero unless the final report passes.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys


PLAN_FILE = "_review_run_plan.json"
EFFECTIVE_PLAN_FILE = "_review_effective_plan.json"
REPORT_FILE = "_review_generated_eval_report.json"
UPDATE_LOG_FILE = "_review_update_log.json"
OUTPUT_FILES = [
    "_conversation_summaries.json",
    "_project_reviews.json",
    "_agent_profile.json",
    "_review_update_log.json",
]


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


def planned_projects(backup_dir):
    plan = load_json(sidecar_path(backup_dir, EFFECTIVE_PLAN_FILE), None)
    if not isinstance(plan, dict):
        plan = load_json(sidecar_path(backup_dir, PLAN_FILE), {})
    return [
        str(project.get("name"))
        for project in (plan.get("projects") or [])
        if isinstance(project, dict) and project.get("name")
    ]


def generated_outputs(backup_dir):
    outputs = [name for name in OUTPUT_FILES if os.path.exists(sidecar_path(backup_dir, name))]
    report_path = sidecar_path(backup_dir, REPORT_FILE)
    if os.path.exists(report_path):
        outputs.append(REPORT_FILE)
    return outputs


def conversation_summary_count(backup_dir, projects):
    doc = load_json(sidecar_path(backup_dir, "_conversation_summaries.json"), {})
    conversations = doc.get("conversations") if isinstance(doc, dict) else {}
    if not isinstance(conversations, dict):
        return 0
    if not projects:
        return len(conversations)
    selected = set(projects)
    return sum(1 for entry in conversations.values() if isinstance(entry, dict) and entry.get("project") in selected)


def task_counts(backup_dir, projects):
    doc = load_json(sidecar_path(backup_dir, "_project_reviews.json"), {})
    reviews = doc.get("projects") if isinstance(doc, dict) else {}
    if not isinstance(reviews, dict):
        return 0
    selected = set(projects) if projects else set(reviews.keys())
    total = 0
    for name, review in reviews.items():
        if name not in selected or not isinstance(review, dict):
            continue
        tasks = review.get("tasks") or []
        if isinstance(tasks, list):
            total += len(tasks)
    return total


def eval_failures(report):
    failures = []
    for check in report.get("checks") or []:
        if not isinstance(check, dict) or check.get("status") != "fail":
            continue
        failures.append({
            "check": check.get("name") or "unknown",
            "failures": (check.get("failures") or [])[:5],
        })
    return failures


def run_eval(trailkeep_repo, backup_dir):
    script = os.path.join(trailkeep_repo, "converters", "eval_generated_reviews.py")
    if not os.path.isfile(script):
        raise FileNotFoundError(f"missing generated eval runner: {script}")
    proc = subprocess.run(
        [sys.executable, script, backup_dir],
        text=True,
        capture_output=True,
    )
    report = load_json(sidecar_path(backup_dir, REPORT_FILE), {})
    return proc, report


def append_update_log(backup_dir, run):
    path = sidecar_path(backup_dir, UPDATE_LOG_FILE)
    doc = load_json(path, {"version": 1, "runs": []})
    if not isinstance(doc, dict):
        doc = {"version": 1, "runs": []}
    runs = doc.get("runs")
    if not isinstance(runs, list):
        runs = []
    runs.insert(0, run)
    doc["version"] = 1
    doc["updated_at"] = run["date"]
    doc["runs"] = runs[:100]
    write_json(path, doc)


def build_run(args, status, report):
    projects = planned_projects(args.backup_dir)
    failures = eval_failures(report)
    errors = []
    for item in failures:
        first = (item.get("failures") or ["generated eval failed"])[0]
        errors.append(f"{item.get('check')}: {first}")
    return {
        "date": now(),
        "status": status,
        "title": args.title,
        "projects": projects,
        "conversation_summaries": conversation_summary_count(args.backup_dir, projects),
        "tasks_total": task_counts(args.backup_dir, projects),
        "requires_approval": False,
        "possible_secret": False,
        "model_provider": args.model_provider or "",
        "model_used": args.model_used or "unknown",
        "model_routing": args.model_routing or "",
        "outputs": generated_outputs(args.backup_dir),
        "eval_report": REPORT_FILE,
        "eval_status": report.get("status") or "unknown",
        "eval_failures": failures,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trailkeep-repo", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--model-provider", default="")
    parser.add_argument("--model-used", default="")
    parser.add_argument("--model-routing", default="")
    parser.add_argument("--title", default="Trailkeep project review")
    args = parser.parse_args()

    trailkeep_repo = os.path.abspath(args.trailkeep_repo)
    backup_dir = os.path.abspath(args.backup_dir)
    if not os.path.isdir(trailkeep_repo):
        print(f"trailkeep repo does not exist: {trailkeep_repo}", file=sys.stderr)
        return 2
    if not os.path.isdir(backup_dir):
        print(f"backup dir does not exist: {backup_dir}", file=sys.stderr)
        return 2
    args.trailkeep_repo = trailkeep_repo
    args.backup_dir = backup_dir

    try:
        first_proc, first_report = run_eval(trailkeep_repo, backup_dir)
    except Exception as exc:
        append_update_log(backup_dir, {
            "date": now(),
            "status": "failed",
            "title": args.title,
            "projects": planned_projects(backup_dir),
            "model_provider": args.model_provider or "",
            "model_used": args.model_used or "unknown",
            "model_routing": args.model_routing or "",
            "outputs": generated_outputs(backup_dir),
            "eval_report": REPORT_FILE,
            "errors": [str(exc)],
        })
        print(str(exc), file=sys.stderr)
        return 1

    status = "ok" if first_proc.returncode == 0 and first_report.get("status") == "pass" else "failed"
    append_update_log(backup_dir, build_run(args, status, first_report))

    final_proc, final_report = run_eval(trailkeep_repo, backup_dir)
    if final_proc.stdout.strip():
        print(final_proc.stdout.strip())
    if final_proc.stderr.strip():
        print(final_proc.stderr.strip(), file=sys.stderr)

    if status != "ok" or final_proc.returncode != 0 or final_report.get("status") != "pass":
        print(f"trailkeep review finalized as failed; see {REPORT_FILE}", file=sys.stderr)
        return 1

    print(f"trailkeep review finalized ok; see {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
