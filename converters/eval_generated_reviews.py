#!/usr/bin/env python3
"""Deterministic evals for generated review sidecars.

Reads the optional coding-agent sidecars after they are generated and writes
`_review_generated_eval_report.json`. No network, no LLM.

Usage: eval_generated_reviews.py <backup_dir>
"""
import datetime
import glob
import hashlib
import json
import os
import re
import sys


REPORT_VERSION = 1
PLAN_FILE = "_review_run_plan.json"
EFFECTIVE_PLAN_FILE = "_review_effective_plan.json"
REPORT_FILE = "_review_generated_eval_report.json"
CONVERSATION_SUMMARIES_FILE = "_conversation_summaries.json"
PROJECT_REVIEWS_FILE = "_project_reviews.json"
AGENT_PROFILE_FILE = "_agent_profile.json"
UPDATE_LOG_FILE = "_review_update_log.json"
PROJECTS_FILE = "_projects.json"
REPO_SYNC_FILE = "_review_repo_sync.json"
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,80}$")
RUN_STATUSES = {"ok", "needs_attention", "needs_approval", "failed"}
ACTION_RE = re.compile(
    r"(?i)\b(add|build|create|design|fix|implement|inspect|review|run|test|"
    r"update|write|refactor|wire|document|summarize|extract|continue|"
    r"agregar|crear|disenar|diseñar|implementar|revisar|actualizar|corregir)\b"
)
VAGUE_RE = re.compile(r"(?i)\b(tbd|todo|later|someday|something|next steps?|continue working)\b")


def now():
    return datetime.datetime.now().astimezone().isoformat()


def load_json(path):
    if not os.path.exists(path):
        return None, "missing"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except Exception as exc:
        return None, str(exc)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def result(name, failures=None, warnings=None, stats=None):
    failures = failures or []
    warnings = warnings or []
    return {
        "name": name,
        "status": "fail" if failures else "pass",
        "failures": failures,
        "warnings": warnings,
        "stats": stats or {},
    }


def iter_string_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_string_values(child)
    elif isinstance(value, str):
        yield value


def contains_secret_value(value):
    for text in iter_string_values(value):
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                return True
    return False


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def meta_value(body, *keys):
    for key in keys:
        m = re.search(rf"{re.escape(key)}\s*:\s*([^|]+?)\s*(?:\||$)", body)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def parse_markdown(path, backup_dir):
    text = open(path, encoding="utf-8", errors="ignore").read()
    comment = re.search(r"<!--(.*?)-->", text, re.S)
    body = comment.group(1) if comment else ""
    rel = os.path.relpath(path, backup_dir)
    title = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        title = m.group(1).strip()
    session_id = meta_value(body, "id") or rel
    project = meta_value(body, "project", "proyecto") or os.path.basename(os.path.dirname(path)) or "(no project)"
    return {
        "id": session_id,
        "relpath": rel,
        "project": project,
        "source": meta_value(body, "source", "fuente") or "",
        "date": meta_value(body, "date", "fecha") or "",
        "title": title,
        "content_hash": content_hash(text),
    }


def load_sessions(backup_dir):
    sessions = []
    for path in sorted(glob.glob(os.path.join(backup_dir, "markdown-*", "**", "*.md"), recursive=True)):
        try:
            sessions.append(parse_markdown(path, backup_dir))
        except Exception:
            continue
    by_key = {}
    for session in sessions:
        by_key[session["id"]] = session
        by_key[session["relpath"]] = session
    return sessions, by_key


def sidecar_path(backup_dir, name):
    return os.path.join(backup_dir, name)


def load_sidecars(backup_dir):
    names = [
        PLAN_FILE,
        CONVERSATION_SUMMARIES_FILE,
        PROJECT_REVIEWS_FILE,
        AGENT_PROFILE_FILE,
        UPDATE_LOG_FILE,
        PROJECTS_FILE,
        REPO_SYNC_FILE,
    ]
    data = {}
    errors = {}
    for name in names:
        doc, err = load_json(sidecar_path(backup_dir, name))
        data[name] = doc
        if err:
            errors[name] = err
    effective_plan, _ = load_json(sidecar_path(backup_dir, EFFECTIVE_PLAN_FILE))
    if isinstance(effective_plan, dict):
        data[EFFECTIVE_PLAN_FILE] = effective_plan
    return data, errors


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def text_value(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("title", "task", "text", "summary", "question", "name", "next_step"):
            if value.get(key):
                return str(value.get(key)).strip()
        return " ".join(str(v) for v in value.values() if isinstance(v, (str, int, float)))
    return str(value).strip()


def selected_projects(plan):
    return as_list(as_dict(plan).get("projects"))


def review_plan(data):
    return data.get(EFFECTIVE_PLAN_FILE) or data.get(PLAN_FILE)


def iter_selected_inputs(plan, input_type=None):
    for project in selected_projects(plan):
        for item in as_list(project.get("selected_inputs")):
            if input_type is None or item.get("type") == input_type:
                yield project, item


def planned_project_names(plan):
    return {str(p.get("name") or "") for p in selected_projects(plan) if p.get("name")}


def project_names_from_data(projects_doc, sessions, plan):
    names = set(planned_project_names(plan))
    for session in sessions:
        if session.get("project"):
            names.add(session["project"])
    projects = as_dict(as_dict(projects_doc).get("projects"))
    names.update(str(k) for k in projects.keys())
    return names


def latest_update_run(update_log):
    runs = as_list(as_dict(update_log).get("runs")) if isinstance(update_log, dict) else []
    return runs[0] if runs else None


def checkpoint_hash_matches(record, expected_hash):
    if isinstance(record, str):
        return record == expected_hash
    if isinstance(record, dict):
        return record.get("content_hash") == expected_hash
    return False


def check_sidecar_presence(data, errors, plan):
    failures = []
    warnings = []
    has_work = bool(selected_projects(plan))
    required = [
        CONVERSATION_SUMMARIES_FILE,
        PROJECT_REVIEWS_FILE,
        AGENT_PROFILE_FILE,
        UPDATE_LOG_FILE,
    ]
    for name in required:
        if errors.get(name) == "missing":
            if name == UPDATE_LOG_FILE:
                warnings.append(f"missing generated sidecar: {name}")
            else:
                (failures if has_work else warnings).append(f"missing generated sidecar: {name}")
        elif errors.get(name):
            failures.append(f"{name} is invalid JSON: {errors[name]}")
    if errors.get(PLAN_FILE):
        failures.append(f"{PLAN_FILE} is missing or invalid: {errors[PLAN_FILE]}")
    return result("sidecar_presence", failures, warnings)


def check_schema(data):
    failures = []
    warnings = []
    summaries = data.get(CONVERSATION_SUMMARIES_FILE)
    reviews = data.get(PROJECT_REVIEWS_FILE)
    profile = data.get(AGENT_PROFILE_FILE)
    update_log = data.get(UPDATE_LOG_FILE)

    if isinstance(summaries, dict):
        if summaries.get("version") != 1:
            failures.append("_conversation_summaries.json version must be 1")
        conversations = summaries.get("conversations")
        if not isinstance(conversations, dict):
            failures.append("_conversation_summaries.json conversations must be an object")
        for sid, entry in as_dict(conversations).items():
            if not isinstance(entry, dict):
                failures.append(f"conversation summary {sid} must be an object")
                continue
            for key in ["project", "source", "date", "content_hash", "summary", "reviewed_at"]:
                if key not in entry:
                    failures.append(f"conversation summary {sid} missing field: {key}")
            for key in ["decisions", "blockers", "task_hints", "files_or_areas"]:
                if key in entry and not isinstance(entry.get(key), list):
                    failures.append(f"conversation summary {sid}.{key} must be a list")

    if isinstance(reviews, dict):
        if reviews.get("version") != 1:
            failures.append("_project_reviews.json version must be 1")
        projects = reviews.get("projects")
        if not isinstance(projects, dict):
            failures.append("_project_reviews.json projects must be an object")
        for name, entry in as_dict(projects).items():
            if not isinstance(entry, dict):
                failures.append(f"project review {name} must be an object")
                continue
            for key in ["summary", "standing_context", "next_step", "roadmap_status", "open_questions", "tasks", "suggested_next_prompt", "design_system", "checkpoints"]:
                if key not in entry:
                    failures.append(f"project review {name} missing field: {key}")
            if "open_questions" in entry and not isinstance(entry.get("open_questions"), list):
                failures.append(f"project review {name}.open_questions must be a list")
            if "tasks" in entry and not isinstance(entry.get("tasks"), list):
                failures.append(f"project review {name}.tasks must be a list")
            if "recommended_repo_doc_updates" in entry:
                updates = entry.get("recommended_repo_doc_updates")
                if not isinstance(updates, list):
                    failures.append(f"project review {name}.recommended_repo_doc_updates must be a list")
                for idx, update in enumerate(as_list(updates)):
                    if not isinstance(update, dict):
                        failures.append(f"project review {name}.recommended_repo_doc_updates[{idx}] must be an object")
                        continue
                    for key in ["file", "reason", "action", "confidence", "requires_user_approval"]:
                        if key not in update:
                            failures.append(f"project review {name}.recommended_repo_doc_updates[{idx}] missing field: {key}")
                    if update.get("requires_user_approval") is not True:
                        failures.append(f"project review {name}.recommended_repo_doc_updates[{idx}] must require user approval")
            if "design_system" in entry and not isinstance(entry.get("design_system"), dict):
                failures.append(f"project review {name}.design_system must be an object")
            checkpoints = entry.get("checkpoints")
            if not isinstance(checkpoints, dict):
                failures.append(f"project review {name}.checkpoints must be an object")
            else:
                for key in ["reviewed_sessions", "reviewed_repo_docs", "reviewed_project_metadata"]:
                    if key in checkpoints and not isinstance(checkpoints.get(key), dict):
                        failures.append(f"project review {name}.checkpoints.{key} must be an object")

    if isinstance(profile, dict):
        if profile.get("version") != 1:
            failures.append("_agent_profile.json version must be 1")
        for key in ["recurring_preferences", "working_style", "repo_conventions", "prompting_patterns", "evidence"]:
            if key in profile and not isinstance(profile.get(key), list):
                failures.append(f"_agent_profile.json {key} must be a list")
        if profile.get("scope") not in (None, "global"):
            warnings.append("_agent_profile.json scope is not global")

    if isinstance(update_log, dict):
        if update_log.get("version") != 1:
            failures.append("_review_update_log.json version must be 1")
        if not isinstance(update_log.get("runs"), list):
            failures.append("_review_update_log.json runs must be a list")
        for idx, run in enumerate(as_list(update_log.get("runs"))):
            if not isinstance(run, dict):
                failures.append(f"_review_update_log.json run {idx} must be an object")
                continue
            status = str(run.get("status") or "").strip().lower()
            if status and status not in RUN_STATUSES:
                failures.append(f"_review_update_log.json run {idx} has invalid status: {status}")
            if "warnings" in run and not isinstance(run.get("warnings"), list):
                failures.append(f"_review_update_log.json run {idx}.warnings must be a list")
            if "eval_warnings" in run and not isinstance(run.get("eval_warnings"), list):
                failures.append(f"_review_update_log.json run {idx}.eval_warnings must be a list")

    return result("schema", failures, warnings)


def check_referential_integrity(data, sessions, session_by_key):
    failures = []
    plan = review_plan(data)
    known_projects = project_names_from_data(data.get(PROJECTS_FILE), sessions, plan)

    summaries = as_dict(as_dict(data.get(CONVERSATION_SUMMARIES_FILE)).get("conversations"))
    for sid, entry in summaries.items():
        if sid not in session_by_key:
            failures.append(f"conversation summary references unknown session: {sid}")
        project = as_dict(entry).get("project")
        if project and project not in known_projects:
            failures.append(f"conversation summary {sid} references unknown project: {project}")

    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))
    for name in reviews.keys():
        if name not in known_projects:
            failures.append(f"project review references unknown project: {name}")

    runs = as_list(as_dict(data.get(UPDATE_LOG_FILE)).get("runs"))
    for idx, run in enumerate(runs):
        projects = as_list(as_dict(run).get("projects"))
        for name in projects:
            if name not in known_projects:
                failures.append(f"update log run {idx} references unknown project: {name}")

    return result(
        "referential_integrity",
        failures,
        stats={"known_projects": len(known_projects), "known_sessions": len(sessions)},
    )


def check_checkpoint_integrity(data):
    failures = []
    plan = review_plan(data)
    summaries = as_dict(as_dict(data.get(CONVERSATION_SUMMARIES_FILE)).get("conversations"))
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))

    for project, item in iter_selected_inputs(plan, "conversation"):
        project_name = project.get("name") or "(unknown project)"
        session_id = item.get("id_or_path")
        session_path = item.get("path")
        expected_hash = item.get("content_hash")
        summary = summaries.get(session_id) or summaries.get(session_path)
        if not summary:
            failures.append(f"{project_name} missing summary for selected conversation {session_id}")
        elif summary.get("content_hash") != expected_hash:
            failures.append(f"{project_name} summary hash mismatch for {session_id}")

        review = reviews.get(project_name)
        if not isinstance(review, dict):
            failures.append(f"{project_name} missing project review entry")
            continue
        checkpoints = as_dict(review.get("checkpoints"))
        reviewed_sessions = as_dict(checkpoints.get("reviewed_sessions"))
        record = reviewed_sessions.get(session_id) or reviewed_sessions.get(session_path)
        if not record:
            failures.append(f"{project_name} missing reviewed_sessions checkpoint for {session_id}")
        elif not checkpoint_hash_matches(record, expected_hash):
            failures.append(f"{project_name} reviewed_sessions hash mismatch for {session_id}")

    for project, item in iter_selected_inputs(plan, "repo_doc"):
        project_name = project.get("name") or "(unknown project)"
        review = reviews.get(project_name)
        if not isinstance(review, dict):
            failures.append(f"{project_name} missing project review entry for repo_doc checkpoint")
            continue
        checkpoints = as_dict(review.get("checkpoints"))
        reviewed_docs = as_dict(checkpoints.get("reviewed_repo_docs"))
        expected_hash = item.get("content_hash")
        keys = [
            item.get("relative_path"),
            item.get("id_or_path"),
            os.path.basename(str(item.get("id_or_path") or "")),
        ]
        record = None
        for key in [k for k in keys if k]:
            if key in reviewed_docs:
                record = reviewed_docs[key]
                break
        if not record:
            failures.append(f"{project_name} missing reviewed_repo_docs checkpoint for {item.get('relative_path') or item.get('id_or_path')}")
        elif not checkpoint_hash_matches(record, expected_hash):
            failures.append(f"{project_name} reviewed_repo_docs hash mismatch for {item.get('relative_path') or item.get('id_or_path')}")

    return result("checkpoint_integrity", failures)


def check_task_stability(data):
    failures = []
    warnings = []
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))
    task_count = 0
    for project_name, review in reviews.items():
        seen = set()
        for idx, task in enumerate(as_list(as_dict(review).get("tasks"))):
            task_count += 1
            if not isinstance(task, dict):
                failures.append(f"{project_name} task {idx} must be an object with a stable id")
                continue
            task_id = str(task.get("id") or "").strip()
            if not task_id:
                failures.append(f"{project_name} task {idx} missing stable id")
                continue
            if task_id in seen:
                failures.append(f"{project_name} duplicate task id: {task_id}")
            seen.add(task_id)
            if not TASK_ID_RE.match(task_id):
                warnings.append(f"{project_name} task id has unstable-looking format: {task_id}")
            if not text_value(task):
                failures.append(f"{project_name} task {task_id} has no readable title/text")
    return result("task_stability", failures, warnings, {"tasks": task_count})


def check_privacy(data):
    failures = []
    warnings = []
    for name in [CONVERSATION_SUMMARIES_FILE, PROJECT_REVIEWS_FILE, AGENT_PROFILE_FILE, UPDATE_LOG_FILE]:
        doc = data.get(name)
        if doc is None:
            continue
        values = list(iter_string_values(doc))
        if contains_secret_value(doc):
            failures.append(f"{name} contains a secret-looking literal")
        emails = []
        for text in values:
            emails.extend(EMAIL_PATTERN.findall(text))
        if emails:
            warnings.append(f"{name} contains email-looking literal(s): {len(set(emails))}")
        if any(".env" in text and re.search(r"(?i)(token|secret|password|api[_-]?key)", text) for text in values):
            failures.append(f"{name} appears to include .env secret context")
    return result("privacy", failures, warnings)


def check_source_precedence(data):
    failures = []
    warnings = []
    plan = review_plan(data)
    repo_docs_by_project = {}
    for project, item in iter_selected_inputs(plan, "repo_doc"):
        repo_docs_by_project.setdefault(project.get("name"), []).append(item)

    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))
    for project_name, docs in repo_docs_by_project.items():
        review = reviews.get(project_name)
        if not isinstance(review, dict):
            failures.append(f"{project_name} has repo docs in plan but no generated review")
            continue
        checkpoints = as_dict(review.get("checkpoints"))
        reviewed_docs = as_dict(checkpoints.get("reviewed_repo_docs"))
        if len(reviewed_docs) < len(docs):
            failures.append(f"{project_name} did not checkpoint every selected repo doc")
        if "open_questions" not in review:
            failures.append(f"{project_name} missing open_questions for repo-doc conflict handling")
        if not text_value(review.get("roadmap_status")) and not text_value(review.get("standing_context")):
            warnings.append(f"{project_name} selected repo docs but generated no roadmap/status context")
    return result("source_precedence", failures, warnings)


def open_questions_mention_repo_stale(review):
    text = " ".join(text_value(item) for item in as_list(as_dict(review).get("open_questions")))
    return bool(re.search(r"(?i)\b(remote|fetch|upstream|stale|behind|sync|sincron)", text))


def check_repo_sync_reflection(data):
    failures = []
    warnings = []
    sync_doc = data.get(REPO_SYNC_FILE)
    if not isinstance(sync_doc, dict):
        return result("repo_sync_reflection", failures, warnings)
    rows = as_dict(sync_doc.get("projects"))
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))
    for project_name, row in rows.items():
        if not isinstance(row, dict):
            continue
        review = as_dict(reviews.get(project_name))
        if row.get("repo_may_be_stale"):
            repo_sync = as_dict(review.get("repo_sync"))
            checkpoints = as_dict(review.get("checkpoints"))
            checkpoint_sync = as_dict(checkpoints.get("repo_sync"))
            reflected = (
                bool(review.get("repo_may_be_stale"))
                or bool(review.get("needs_deep_review"))
                or bool(repo_sync.get("repo_may_be_stale"))
                or bool(checkpoint_sync.get("repo_may_be_stale"))
                or open_questions_mention_repo_stale(review)
            )
            if not reflected:
                failures.append(f"{project_name} has remote commits ahead but review did not mark repo_may_be_stale, needs_deep_review, repo_sync, or an open question")
        if row.get("sync_uncertain") and project_name in reviews and not open_questions_mention_repo_stale(review):
            warnings.append(f"{project_name} repo sync was uncertain but review has no open question about repo freshness")
    return result("repo_sync_reflection", failures, warnings)


def check_actionability(data):
    failures = []
    warnings = []
    plan = review_plan(data)
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))
    for project_name in sorted(planned_project_names(plan)):
        review = reviews.get(project_name)
        if not isinstance(review, dict):
            failures.append(f"{project_name} missing review for actionability")
            continue
        next_step = text_value(review.get("next_step"))
        prompt = text_value(review.get("suggested_next_prompt"))
        if len(next_step) < 12:
            failures.append(f"{project_name} next_step is missing or too short")
        if len(prompt) < 40:
            failures.append(f"{project_name} suggested_next_prompt is missing or too short")
        if next_step and not ACTION_RE.search(next_step):
            warnings.append(f"{project_name} next_step has no obvious action verb")
        if prompt and VAGUE_RE.fullmatch(prompt.strip()):
            failures.append(f"{project_name} suggested_next_prompt is vague")
    return result("actionability", failures, warnings)


def check_update_log(data, prior_failed):
    failures = []
    warnings = []
    plan = review_plan(data)
    update_log = data.get(UPDATE_LOG_FILE)
    runs = as_list(as_dict(update_log).get("runs"))
    has_work = bool(selected_projects(plan))
    if has_work and not runs:
        warnings.append("missing update log run for generated sidecars")
        return result("update_log", failures, warnings)

    latest = latest_update_run(update_log)
    if latest:
        status = str(as_dict(latest).get("status") or "").lower()
        errors = as_list(as_dict(latest).get("errors"))
        run_warnings = as_list(as_dict(latest).get("warnings"))
        model_used = str(as_dict(latest).get("model_used") or "").strip().lower()
        successful = status in ("ok", "needs_attention")
        if successful and errors:
            failures.append("latest update log run is successful but contains errors")
        if successful and prior_failed:
            failures.append("latest update log run is successful but generated-output evals failed")
        if status == "ok" and run_warnings:
            failures.append("latest update log run is ok but contains warnings; use needs_attention")
        if status == "needs_attention" and not run_warnings:
            warnings.append("latest update log run needs_attention but does not include warnings")
        if successful and model_used in ("", "unknown"):
            warnings.append("latest update log run does not record a concrete model_used")
        if not status:
            failures.append("latest update log run missing status")
    elif not has_work:
        warnings.append("no update log run; no planned generated work found")

    return result("update_log", failures, warnings, {"runs": len(runs)})


def run_checks(data, errors, sessions, session_by_key):
    base_checks = [
        check_sidecar_presence(data, errors, review_plan(data)),
        check_schema(data),
        check_referential_integrity(data, sessions, session_by_key),
        check_checkpoint_integrity(data),
        check_task_stability(data),
        check_privacy(data),
        check_source_precedence(data),
        check_repo_sync_reflection(data),
        check_actionability(data),
    ]
    prior_failed = any(c["status"] == "fail" for c in base_checks)
    return base_checks + [check_update_log(data, prior_failed)]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    backup_dir = sys.argv[1]
    data, errors = load_sidecars(backup_dir)
    sessions, session_by_key = load_sessions(backup_dir)
    checks = run_checks(data, errors, sessions, session_by_key)
    failed = [c for c in checks if c["status"] == "fail"]
    warnings = sum(len(c.get("warnings") or []) for c in checks)
    report = {
        "version": REPORT_VERSION,
        "generated_at": now(),
        "scope": "generated_reviews",
        "status": "fail" if failed else "pass",
        "plan_path": EFFECTIVE_PLAN_FILE if data.get(EFFECTIVE_PLAN_FILE) else PLAN_FILE,
        "plan_generated_at": as_dict(review_plan(data)).get("generated_at"),
        "report_file": REPORT_FILE,
        "checks": checks,
        "summary": {
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "failed": len(failed),
            "warnings": warnings,
        },
        "notes": [
            "No model calls were made.",
            "This report validates generated sidecars after the optional coding-agent automation writes them.",
        ],
    }
    write_json(sidecar_path(backup_dir, REPORT_FILE), report)
    print(f"Generated review eval: {report['status']} ({report['summary']['passed']} passed, {report['summary']['failed']} failed, {warnings} warnings)")
    if failed:
        for check in failed[:3]:
            print(f"  {check['name']}: {check['failures'][0]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
