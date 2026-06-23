#!/usr/bin/env python3
"""Gate model calls for a trailkeep generated review run.

Reads `_review_run_plan.json`, `_review_eval_report.json`, and `log.json`, then
exits:

- 0 when model calls may proceed;
- 1 when deterministic planner evals failed, required files are invalid, or the
  latest backup run is stale;
- 2 when user approval is required before model calls.

The output never includes raw selected input content.
"""
import argparse
import copy
import datetime
import json
import os
import sys


PLAN_FILE = "_review_run_plan.json"
PLAN_EVAL_FILE = "_review_eval_report.json"
UPDATE_LOG_FILE = "_review_update_log.json"
BACKUP_LOG_FILE = "log.json"
DECISIONS_FILE = "_review_gate_decisions.json"
EFFECTIVE_PLAN_FILE = "_review_effective_plan.json"


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


def parse_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":
        candidates.append(text[:-2] + ":" + text[-2:])
    for candidate in candidates:
        try:
            parsed = datetime.datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.datetime.now().astimezone().tzinfo)
            return parsed.astimezone()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.datetime.strptime(text, fmt).astimezone()
        except ValueError:
            pass
    return None


def timestamp_freshness(label, value, max_age_hours):
    parsed = parse_timestamp(value)
    if not parsed:
        return None, None, [f"{label} has invalid date: {value}"]
    age_hours = (datetime.datetime.now().astimezone() - parsed).total_seconds() / 3600.0
    if age_hours < -0.25:
        return None, None, [f"{label} is in the future: {value}"]
    if age_hours > max_age_hours:
        return None, None, [f"{label} is {age_hours:.1f}h old; rerun trailkeep backup first"]
    return {"date": value, "age_hours": round(max(age_hours, 0.0), 2), "max_age_hours": max_age_hours}, parsed, []


def backup_freshness(backup_dir, max_age_hours):
    path = sidecar_path(backup_dir, BACKUP_LOG_FILE)
    log = load_json(path, None)
    if not isinstance(log, list) or not log:
        return None, None, [f"missing or invalid {BACKUP_LOG_FILE}; run trailkeep backup before review"]
    latest = log[0]
    if not isinstance(latest, dict):
        return None, None, [f"{BACKUP_LOG_FILE} latest entry is invalid"]
    backup_date = latest.get("date")
    status, parsed, errors = timestamp_freshness(f"{BACKUP_LOG_FILE} latest entry", backup_date, max_age_hours)
    if errors:
        if errors[0].startswith(f"{BACKUP_LOG_FILE} latest entry is"):
            errors = [
                errors[0].replace(
                    "rerun trailkeep backup first",
                    "run backup first or schedule review after the daily update",
                )
            ]
        return None, None, errors
    return {
        "backup_log": BACKUP_LOG_FILE,
        "backup_date": backup_date,
        "backup_age_hours": status["age_hours"],
        "max_backup_age_hours": max_age_hours,
    }, parsed, []


def preflight_freshness(plan, report, backup_date, max_age_hours, max_skew_minutes):
    errors = []
    plan_status, plan_date, plan_errors = timestamp_freshness("review plan generated_at", plan.get("generated_at"), max_age_hours)
    report_status, report_date, report_errors = timestamp_freshness("review eval generated_at", report.get("generated_at"), max_age_hours)
    errors.extend(plan_errors)
    errors.extend(report_errors)
    if report.get("plan_generated_at") != plan.get("generated_at"):
        errors.append("review eval does not match the current review plan; rerun trailkeep backup")
    if backup_date and plan_date:
        minutes_before_backup = (backup_date - plan_date).total_seconds() / 60.0
        if minutes_before_backup > max_skew_minutes:
            errors.append(
                f"review plan was generated {minutes_before_backup:.1f} minutes before the latest backup log; rerun trailkeep backup"
            )
    return {
        "plan_generated_at": plan.get("generated_at"),
        "plan_age_hours": plan_status["age_hours"] if plan_status else None,
        "eval_generated_at": report.get("generated_at"),
        "eval_age_hours": report_status["age_hours"] if report_status else None,
        "max_plan_backup_skew_minutes": max_skew_minutes,
    }, errors


def projects(plan):
    rows = plan.get("projects") if isinstance(plan, dict) else []
    return rows if isinstance(rows, list) else []


def project_names(plan):
    return [
        str(project.get("name"))
        for project in projects(plan)
        if isinstance(project, dict) and project.get("name")
    ]


def failed_checks(report):
    checks = report.get("checks") if isinstance(report, dict) else []
    failures = []
    for check in checks or []:
        if not isinstance(check, dict) or check.get("status") != "fail":
            continue
        failures.append({
            "check": check.get("name") or "unknown",
            "failures": (check.get("failures") or [])[:5],
        })
    return failures


def flagged_inputs(plan):
    rows = []
    for project in projects(plan):
        if not isinstance(project, dict):
            continue
        name = project.get("name") or "(unknown project)"
        project_flagged = bool(project.get("requires_approval") or project.get("possible_secret"))
        inputs = []
        for item in project.get("selected_inputs") or []:
            if not isinstance(item, dict):
                continue
            if item.get("possible_secret") or project_flagged:
                inputs.append({
                    "key": input_key(name, item),
                    "type": item.get("type") or "",
                    "id_or_path": item.get("id_or_path") or item.get("path") or "",
                    "content_hash": item.get("content_hash") or "",
                    "reason": item.get("reason") or "",
                    "possible_secret": bool(item.get("possible_secret")),
                })
        if project_flagged or inputs:
            rows.append({
                "project": name,
                "requires_approval": bool(project.get("requires_approval")),
                "possible_secret": bool(project.get("possible_secret")),
                "inputs": inputs,
            })
    return rows


def input_key(project, item):
    if not isinstance(item, dict):
        item = {}
    return "\x1f".join([
        str(project or ""),
        str(item.get("type") or ""),
        str(item.get("id_or_path") or item.get("path") or ""),
        str(item.get("content_hash") or ""),
    ])


def public_input_key(key):
    return str(key).replace("\x1f", "|")


def key_from_decision(value):
    if isinstance(value, str):
        return value.replace("|", "\x1f")
    if isinstance(value, dict):
        if any(k in value for k in ("project", "type", "id_or_path", "path", "content_hash")):
            return input_key(value.get("project"), value)
        if value.get("key"):
            return str(value.get("key")).replace("|", "\x1f")
    return ""


def flatten_flagged(flagged):
    rows = []
    for project in flagged:
        for item in project.get("inputs") or []:
            key = item.get("key") or input_key(project.get("project"), item)
            row = dict(item)
            row["project"] = project.get("project") or ""
            row["requires_approval"] = bool(project.get("requires_approval"))
            row["key"] = key
            row["public_key"] = public_input_key(key)
            rows.append(row)
    return rows


def decision_entries(doc, plan_generated_at):
    if not isinstance(doc, dict):
        return []
    entries = []
    plans = doc.get("plans")
    if isinstance(plans, dict):
        entry = plans.get(str(plan_generated_at or ""))
        if isinstance(entry, dict):
            entries.append(entry)
    for entry in doc.get("decisions") or []:
        if isinstance(entry, dict) and str(entry.get("plan_generated_at") or "") == str(plan_generated_at or ""):
            entries.append(entry)
    return entries


def approval_resolution(backup_dir, plan, flagged):
    flattened = flatten_flagged(flagged)
    flagged_keys = {row["key"] for row in flattened}
    doc = load_json(sidecar_path(backup_dir, DECISIONS_FILE), {})
    approved = set()
    excluded = set()
    stopped = False
    for entry in decision_entries(doc, plan.get("generated_at")):
        if entry.get("stop") or str(entry.get("decision") or "").lower() == "stop":
            stopped = True
        if entry.get("approve_all"):
            approved.update(flagged_keys)
        for value in entry.get("approved_inputs") or []:
            key = key_from_decision(value)
            if key:
                approved.add(key)
        for value in entry.get("excluded_inputs") or []:
            key = key_from_decision(value)
            if key:
                excluded.add(key)
    approved &= flagged_keys
    excluded &= flagged_keys
    unresolved = [row for row in flattened if row["key"] not in approved and row["key"] not in excluded]
    return {
        "stopped": stopped,
        "approved": approved,
        "excluded": excluded,
        "unresolved": unresolved,
        "flagged": flattened,
    }


def public_decision_rows(rows):
    result = []
    for row in rows:
        result.append({
            "key": row.get("public_key") or public_input_key(row.get("key")),
            "project": row.get("project") or "",
            "type": row.get("type") or "",
            "id_or_path": row.get("id_or_path") or "",
            "content_hash": row.get("content_hash") or "",
            "reason": row.get("reason") or "",
            "requires_approval": bool(row.get("requires_approval")),
            "possible_secret": bool(row.get("possible_secret")),
        })
    return result


def decision_template(plan, unresolved):
    public_rows = public_decision_rows(unresolved)
    return {
        "version": 1,
        "updated_at": now(),
        "plans": {
            str(plan.get("generated_at") or ""): {
                "decided_at": now(),
                "approved_inputs": public_rows,
                "excluded_inputs": [],
                "note": "Move any input objects you do not approve from approved_inputs to excluded_inputs, or set stop=true.",
            }
        },
    }


def write_effective_plan(backup_dir, plan, excluded):
    effective = copy.deepcopy(plan)
    excluded_public = []
    for project in effective.get("projects") or []:
        if not isinstance(project, dict):
            continue
        name = project.get("name") or ""
        kept = []
        for item in project.get("selected_inputs") or []:
            key = input_key(name, item)
            if key in excluded:
                excluded_public.append(public_input_key(key))
                continue
            kept.append(item)
        project["selected_inputs"] = kept
    effective["effective_plan"] = True
    effective["source_plan_generated_at"] = plan.get("generated_at")
    effective["gate_checked_at"] = now()
    effective["excluded_inputs"] = excluded_public
    write_json(sidecar_path(backup_dir, EFFECTIVE_PLAN_FILE), effective)
    return excluded_public


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


def maybe_log(args, status, plan, payload):
    if args.no_write_log:
        return
    run = {
        "date": now(),
        "status": status,
        "title": "Trailkeep project review gate",
        "projects": project_names(plan),
        "requires_approval": status == "needs_approval",
        "possible_secret": bool(payload.get("flagged_inputs")),
        "approval_inputs": payload.get("flagged_inputs") or [],
        "model_provider": "",
        "model_used": "none",
        "model_routing": "",
        "outputs": [],
        "errors": payload.get("errors") or [],
    }
    append_update_log(args.backup_dir, run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--max-backup-age-hours", type=float, default=24.0)
    parser.add_argument("--max-plan-backup-skew-minutes", type=float, default=120.0)
    parser.add_argument("--no-write-log", action="store_true")
    args = parser.parse_args()
    args.backup_dir = os.path.abspath(args.backup_dir)
    if not os.path.isdir(args.backup_dir):
        print(json.dumps({"status": "failed", "errors": [f"backup dir does not exist: {args.backup_dir}"]}))
        return 1

    plan = load_json(sidecar_path(args.backup_dir, PLAN_FILE), None)
    report = load_json(sidecar_path(args.backup_dir, PLAN_EVAL_FILE), None)
    if not isinstance(plan, dict):
        payload = {"status": "failed", "errors": [f"missing or invalid {PLAN_FILE}"]}
        maybe_log(args, "failed", {}, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    if not isinstance(report, dict):
        payload = {"status": "failed", "projects": project_names(plan), "errors": [f"missing or invalid {PLAN_EVAL_FILE}"]}
        maybe_log(args, "failed", plan, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    backup_status, backup_date, backup_errors = backup_freshness(args.backup_dir, args.max_backup_age_hours)
    if backup_errors:
        payload = {
            "status": "failed",
            "projects": project_names(plan),
            "errors": backup_errors,
        }
        maybe_log(args, "failed", plan, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    preflight_status, preflight_errors = preflight_freshness(
        plan,
        report,
        backup_date,
        args.max_backup_age_hours,
        args.max_plan_backup_skew_minutes,
    )
    if preflight_errors:
        payload = {
            "status": "failed",
            "projects": project_names(plan),
            "backup_status": backup_status,
            "preflight_status": preflight_status,
            "errors": preflight_errors,
        }
        maybe_log(args, "failed", plan, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    failures = failed_checks(report)
    if report.get("status") == "fail" or failures:
        payload = {
            "status": "failed",
            "projects": project_names(plan),
            "errors": [f"{item['check']}: {(item.get('failures') or ['failed'])[0]}" for item in failures] or ["planner eval failed"],
            "failed_checks": failures,
        }
        maybe_log(args, "failed", plan, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    flagged = flagged_inputs(plan)
    if flagged:
        approval = approval_resolution(args.backup_dir, plan, flagged)
        if approval["stopped"]:
            payload = {
                "status": "failed",
                "projects": project_names(plan),
                "errors": ["review run stopped by user approval decision"],
            }
            maybe_log(args, "failed", plan, payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        if not approval["unresolved"]:
            excluded_public = write_effective_plan(args.backup_dir, plan, approval["excluded"])
            payload = {
                "status": "ok",
                "projects": project_names(plan),
                "backup_status": backup_status,
                "preflight_status": preflight_status,
                "effective_plan": EFFECTIVE_PLAN_FILE,
                "approved_inputs": [public_input_key(key) for key in sorted(approval["approved"])],
                "excluded_inputs": excluded_public,
                "message": "Approval is resolved. Model calls may proceed using the effective review plan.",
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        payload = {
            "status": "needs_approval",
            "projects": project_names(plan),
            "flagged_inputs": public_decision_rows(approval["unresolved"]),
            "all_flagged_inputs": public_decision_rows(approval["flagged"]),
            "unresolved_inputs": public_decision_rows(approval["unresolved"]),
            "decision_file": DECISIONS_FILE,
            "decision_template": decision_template(plan, approval["unresolved"]),
            "message": "Approval is required before any model call. No raw input content is shown.",
        }
        maybe_log(args, "needs_approval", plan, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    write_effective_plan(args.backup_dir, plan, set())
    payload = {
        "status": "ok",
        "projects": project_names(plan),
        "backup_status": backup_status,
        "preflight_status": preflight_status,
        "effective_plan": EFFECTIVE_PLAN_FILE,
        "message": "Model calls may proceed using only selected inputs from the effective review plan.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
