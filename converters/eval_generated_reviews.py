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
SUMMARY_QUALITY_VERSION = "actionable-v2"
SEMANTIC_SAMPLE_EVERY = 25
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
SEMANTIC_QUALITY_STATUSES = {"pass", "needs_attention", "skipped"}
EVIDENCE_REF_TYPES = {
    "conversation",
    "conversation_summary",
    "repo_doc",
    "metadata",
    "repo_sync",
    "project_review",
    "agent_profile",
    "tool",
    "instruction_context",
}
TASK_SOURCES = {"roadmap", "repo_doc", "conversation", "project_review", "inferred"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
MAX_EVIDENCE_QUOTE_CHARS = 280
SUMMARY_SIGNAL_LEVELS = {
    "administrative",
    "low_signal",
    "context_dependent",
    "decision",
    "implementation",
    "blocker",
}
LOW_SIGNAL_LEVELS = {"administrative", "low_signal", "context_dependent"}
ACTION_RE = re.compile(
    r"(?i)\b(add|build|create|design|fix|implement|inspect|review|run|test|"
    r"update|write|refactor|wire|document|summarize|extract|continue|"
    r"agregar|crear|disenar|diseñar|implementar|revisar|actualizar|corregir)\b"
)
VAGUE_RE = re.compile(r"(?i)\b(tbd|todo|later|someday|something|next steps?|continue working)\b")
PROMPT_BOILERPLATE_RE = re.compile(
    r"(?i)\b("
    r"review\s+(the\s+)?trailkeep generated sidecars|"
    r"compare\s+(the\s+)?open tasks\s+with\s+(the\s+)?repo planning docs|"
    r"choose one focused follow-up|"
    r"highest-priority next step|"
    r"validate it against repo docs"
    r")\b"
)
PROMPT_TARGET_RE = re.compile(
    r"(?ix)"
    r"(\b[\w./-]+\.(?:md|py|js|cjs|mjs|ts|tsx|jsx|html|css|json|sh|yml|yaml|toml)\b|"
    r"\b(?:section|view|screen|component|flow|panel|card|sidebar|dashboard|"
    r"seccion|sección|vista|pantalla|componente|flujo|tarjeta|barra lateral|tablero)\b)"
)
PROMPT_VERIFY_RE = re.compile(
    r"(?i)\b(run|verify|validate|test|check|assert|qa|manual verification|screenshot|"
    r"playwright|lint|build|py_compile|pytest|node|npm|pnpm|python|"
    r"verificar|validar|probar|testear|chequear|captura|verificacion manual|verificación manual)\b"
)
PROMPT_OUTPUT_RE = re.compile(
    r"(?is)\b(update|write|record|report|document|commit|append|merge|return|leave|create|"
    r"actualizar|escribir|registrar|reportar|documentar|commitear|crear)\b"
    r".{0,160}\b(sidecar|_project_reviews|_conversation_summaries|roadmap|backlog|todo|docs?|"
    r"tests?|fixture|eval|viewer|file|output|result|archivo|salida|resultado)\b"
)
SUMMARY_BOILERPLATE_RE = re.compile(
    r"(?i)\b("
    r"bootstrap summary for|"
    r"selected because new or changed conversation|"
    r"evidence clusters around|"
    r"noted areas include|"
    r"secret-like content was read from|"
    r"deterministic redacted preprocessed input"
    r")\b"
)
INSTRUCTION_CONTEXT_POLLUTION_RE = re.compile(
    r"(?i)\b("
    r"AGENTS\.md instructions for|"
    r"Codex Context \(Global\)|"
    r"Global verification standard|"
    r"Evidence before claims|"
    r"Global UI product standards|"
    r"Global security and data integrity|"
    r"Non-negotiable rules|"
    r"INSTRUCTION_CONTEXT_\d+|"
    r"instruction_context|"
    r"permissions instructions|"
    r"environment_context|"
    r"skills_instructions|"
    r"plugins_instructions|"
    r"developer/system context"
    r")\b"
)
ROLE_MARKER_POLLUTION_RE = re.compile(
    r"(?i)\b(claude|codex|cursor|opencode|assistant|user|you)\b"
    r"(?:\s+\b(claude|codex|cursor|opencode|assistant|user|you)\b){2,}"
)
SUMMARY_SERIALIZED_OBJECT_RE = re.compile(r"^\s*[\{\[]|['\"](?:project|source|content_hash|summary)['\"]\s*:")
TOOL_EVIDENCE_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"implemented|fixed|changed|added|created|wrote|edited|updated|removed|"
    r"refactored|ran|tested|verified|passed|failed|built|committed|pushed|"
    r"errored|applied|compiled|deployed|"
    r"implement[oó]|arregl[oó]|corrigi[oó]|agreg[oó]|cre[oó]|escribi[oó]|"
    r"edit[oó]|actualiz[oó]|quit[oó]|refactoriz[oó]|corri[oó]|prob[oó]|"
    r"verific[oó]|pas[oó]|fall[oó]|compil[oó]|commite[oó]|pushe[oó]"
    r")\b"
)
RAW_TOOL_OUTPUT_RE = re.compile(
    r"(?im)(^\s*\[(tool|result|herramienta|resultado)\b|^\s*```(?:bash|sh|zsh|console)?\s*$)"
)


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
    sessions = canonical_sessions(sessions)
    by_key = {}
    for session in sessions:
        stable_key = session_stable_key(session)
        if stable_key:
            by_key[stable_key] = session
        by_key[session["id"]] = session
        by_key[session["relpath"]] = session
    return sessions, by_key


def session_stable_key(session):
    sid = text_value(as_dict(session).get("id"))
    source = text_value(as_dict(session).get("source"))
    if not sid or not source:
        return ""
    return f"{source}:{sid}"


def session_newer_than(left, right):
    left_key = (
        text_value(left.get("date")),
        text_value(left.get("content_hash")),
        text_value(left.get("relpath")),
    )
    right_key = (
        text_value(right.get("date")),
        text_value(right.get("content_hash")),
        text_value(right.get("relpath")),
    )
    return left_key > right_key


def canonical_sessions(sessions):
    best_by_key = {}
    without_key = []
    for session in sessions:
        key = session_stable_key(session)
        if not key:
            without_key.append(session)
            continue
        current = best_by_key.get(key)
        if current is None or session_newer_than(session, current):
            best_by_key[key] = session
    return without_key + list(best_by_key.values())


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


def evidence_refs(value):
    return value if isinstance(value, list) else []


def evidence_ref_target(ref):
    if not isinstance(ref, dict):
        return ""
    for key in ("id_or_path", "relative_path", "path", "session_id", "project", "field", "tool_name", "command", "status"):
        value = text_value(ref.get(key))
        if value:
            return value
    return ""


def validate_evidence_refs(refs, context, failures, *, allowed_types=None, require_content_hash=False):
    if not isinstance(refs, list) or not refs:
        failures.append(f"{context} missing evidence_refs")
        return
    for idx, ref in enumerate(refs):
        label = f"{context}.evidence_refs[{idx}]"
        if not isinstance(ref, dict):
            failures.append(f"{label} must be an object")
            continue
        ref_type = text_value(ref.get("type"))
        if ref_type not in EVIDENCE_REF_TYPES:
            failures.append(f"{label} has invalid type: {ref_type or '(missing)'}")
        elif allowed_types and ref_type not in allowed_types:
            failures.append(f"{label} has unsupported type for this context: {ref_type}")
        if not evidence_ref_target(ref):
            failures.append(f"{label} must identify an input, path, project, or field")
        if require_content_hash and not text_value(ref.get("content_hash")):
            failures.append(f"{label} missing content_hash")
        quote = text_value(ref.get("quote"))
        if len(quote) > MAX_EVIDENCE_QUOTE_CHARS:
            failures.append(f"{label}.quote exceeds {MAX_EVIDENCE_QUOTE_CHARS} characters")
        if contains_secret_value(ref):
            failures.append(f"{label} contains a secret-looking literal")


def has_tool_evidence(refs):
    return any(isinstance(ref, dict) and text_value(ref.get("type")) == "tool" for ref in evidence_refs(refs))


def has_instruction_context_evidence(refs):
    return any(
        isinstance(ref, dict) and text_value(ref.get("type")) == "instruction_context"
        for ref in evidence_refs(refs)
    )


def needs_tool_evidence(text):
    return bool(TOOL_EVIDENCE_CLAIM_RE.search(text_value(text)))


def append_tool_policy_failure(failures, context, refs, text):
    if needs_tool_evidence(text) and not has_tool_evidence(refs):
        failures.append(f"{context} makes execution/verification claims without tool evidence")


def instruction_context_polluted(text):
    return bool(INSTRUCTION_CONTEXT_POLLUTION_RE.search(text_value(text)))


def append_instruction_text_failure(failures, context, text):
    if instruction_context_polluted(text):
        failures.append(f"{context} treats instruction/header context as conversation content")


def append_instruction_ref_failure(failures, context, refs):
    if has_instruction_context_evidence(refs):
        failures.append(f"{context} uses instruction_context evidence for product work")


def project_review_text_fields(review):
    fields = [
        ("summary", review.get("summary")),
        ("standing_context", review.get("standing_context")),
        ("next_step", review.get("next_step")),
        ("roadmap_status", review.get("roadmap_status")),
        ("suggested_next_prompt", review.get("suggested_next_prompt")),
    ]
    design = as_dict(review.get("design_system"))
    if design:
        fields.append(("design_system.summary", design.get("summary")))
        for idx, value in enumerate(as_list(design.get("rules"))):
            fields.append((f"design_system.rules[{idx}]", value))
        for idx, value in enumerate(as_list(design.get("components"))):
            fields.append((f"design_system.components[{idx}]", value))
    for idx, question in enumerate(as_list(review.get("open_questions"))):
        fields.append((f"open_questions[{idx}]", question))
    for idx, task in enumerate(as_list(review.get("tasks"))):
        fields.append((f"tasks[{idx}]", task))
    for idx, update in enumerate(as_list(review.get("recommended_repo_doc_updates"))):
        fields.append((f"recommended_repo_doc_updates[{idx}]", update))
    return fields


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
            for key in [
                "project",
                "source",
                "date",
                "content_hash",
                "evidence_refs",
                "summary",
                "reviewed_at",
                "summary_quality_version",
                "signal_level",
                "include_in_project_rollup",
            ]:
                if key not in entry:
                    failures.append(f"conversation summary {sid} missing field: {key}")
            for key in ["decisions", "blockers", "task_hints", "files_or_areas"]:
                if key in entry and not isinstance(entry.get(key), list):
                    failures.append(f"conversation summary {sid}.{key} must be a list")
            if "evidence_refs" in entry and not isinstance(entry.get("evidence_refs"), list):
                failures.append(f"conversation summary {sid}.evidence_refs must be a list")
            if "summary" in entry and not isinstance(entry.get("summary"), str):
                failures.append(f"conversation summary {sid}.summary must be a string")
            if "include_in_project_rollup" in entry and not isinstance(entry.get("include_in_project_rollup"), bool):
                failures.append(f"conversation summary {sid}.include_in_project_rollup must be a boolean")

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
            for key in [
                "summary",
                "summary_evidence_refs",
                "standing_context",
                "next_step",
                "next_step_evidence_refs",
                "roadmap_status",
                "roadmap_status_evidence_refs",
                "open_questions",
                "tasks",
                "suggested_next_prompt",
                "design_system",
                "checkpoints",
            ]:
                if key not in entry:
                    failures.append(f"project review {name} missing field: {key}")
            for key in [
                "evidence_refs",
                "summary_evidence_refs",
                "standing_context_evidence_refs",
                "next_step_evidence_refs",
                "roadmap_status_evidence_refs",
            ]:
                if key in entry and not isinstance(entry.get(key), list):
                    failures.append(f"project review {name}.{key} must be a list")
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
                    if "evidence_refs" in update and not isinstance(update.get("evidence_refs"), list):
                        failures.append(f"project review {name}.recommended_repo_doc_updates[{idx}].evidence_refs must be a list")
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


def check_conversation_summary_quality(data):
    failures = []
    warnings = []
    summaries = as_dict(as_dict(data.get(CONVERSATION_SUMMARIES_FILE)).get("conversations"))
    stats = {
        "summaries": len(summaries),
        "rollup_included": 0,
        "low_signal": 0,
    }
    for sid, entry in summaries.items():
        if not isinstance(entry, dict):
            continue
        version = str(entry.get("summary_quality_version") or "").strip()
        signal = str(entry.get("signal_level") or "").strip()
        summary = text_value(entry.get("summary"))
        decisions = as_list(entry.get("decisions"))
        blockers = as_list(entry.get("blockers"))
        task_hints = as_list(entry.get("task_hints"))
        include = entry.get("include_in_project_rollup")

        if version != SUMMARY_QUALITY_VERSION:
            failures.append(
                f"conversation summary {sid} has stale summary_quality_version: {version or '(missing)'}"
            )
        if signal not in SUMMARY_SIGNAL_LEVELS:
            failures.append(f"conversation summary {sid} has invalid signal_level: {signal or '(missing)'}")
        if include is True:
            stats["rollup_included"] += 1
        if signal in LOW_SIGNAL_LEVELS:
            stats["low_signal"] += 1
        if not summary:
            failures.append(f"conversation summary {sid} has empty summary")
            continue
        if RAW_TOOL_OUTPUT_RE.search(summary):
            failures.append(f"conversation summary {sid} includes raw tool output or code fence")
        if SUMMARY_BOILERPLATE_RE.search(summary):
            failures.append(f"conversation summary {sid} contains bootstrap/boilerplate summary text")
        if instruction_context_polluted(summary):
            failures.append(f"conversation summary {sid} contains instruction/header context as summary text")
        for label, values in [
            ("decisions", decisions),
            ("blockers", blockers),
            ("task_hints", task_hints),
        ]:
            if any(instruction_context_polluted(value) for value in values):
                failures.append(f"conversation summary {sid}.{label} contains instruction/header context")
        if ROLE_MARKER_POLLUTION_RE.search(summary):
            failures.append(f"conversation summary {sid} contains role-marker pollution")
        if SUMMARY_SERIALIZED_OBJECT_RE.search(summary):
            failures.append(f"conversation summary {sid} looks like a serialized object, not a readable summary")
        if signal in LOW_SIGNAL_LEVELS:
            if include is True:
                failures.append(f"conversation summary {sid} is low-signal but included in project rollup")
            if decisions or blockers or task_hints:
                failures.append(f"conversation summary {sid} is low-signal but invents decisions, blockers, or task hints")
        elif include is False:
            warnings.append(f"conversation summary {sid} has durable signal but is excluded from project rollup")
        if signal in {"decision", "implementation", "blocker"} and len(summary) < 40:
            warnings.append(f"conversation summary {sid} has durable signal but very short summary")
    return result("conversation_summary_quality", failures, warnings, stats)


def check_project_review_quality(data):
    failures = []
    warnings = []
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))
    checked_fields = 0
    for project_name, review in reviews.items():
        if not isinstance(review, dict):
            continue
        for field, value in project_review_text_fields(review):
            text = text_value(value)
            if not text:
                continue
            checked_fields += 1
            context = f"{project_name}.{field}"
            if SUMMARY_BOILERPLATE_RE.search(text):
                failures.append(f"{context} contains bootstrap/boilerplate review text")
            if ROLE_MARKER_POLLUTION_RE.search(text):
                failures.append(f"{context} contains role-marker pollution")
            if SUMMARY_SERIALIZED_OBJECT_RE.search(text):
                failures.append(f"{context} looks like a serialized object, not readable review text")
            if RAW_TOOL_OUTPUT_RE.search(text):
                failures.append(f"{context} includes raw tool output")
        next_step = text_value(review.get("next_step"))
        summary = text_value(review.get("summary"))
        if summary and next_step and summary == next_step:
            warnings.append(f"{project_name} summary and next_step are identical")
    return result("project_review_quality", failures, warnings, {"checked_fields": checked_fields})


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
        elif summary.get("summary_quality_version") != SUMMARY_QUALITY_VERSION:
            failures.append(f"{project_name} summary quality version mismatch for {session_id}")

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
        elif isinstance(record, dict) and record.get("summary_quality_version") != SUMMARY_QUALITY_VERSION:
            failures.append(f"{project_name} reviewed_sessions quality version mismatch for {session_id}")

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


def check_incrementality(data):
    failures = []
    warnings = []
    plan = review_plan(data)
    planned = planned_project_names(plan)
    latest = latest_update_run(data.get(UPDATE_LOG_FILE))
    run_projects = {
        str(name)
        for name in as_list(as_dict(latest).get("projects"))
        if str(name or "").strip()
    } if latest else set()
    if planned and run_projects:
        unexpected = sorted(run_projects - planned)
        if unexpected:
            failures.append(
                "latest update log includes project(s) outside the selected review plan: "
                + ", ".join(unexpected)
            )
    elif planned and latest:
        warnings.append("latest update log has no affected projects")
    return result(
        "incrementality",
        failures,
        warnings,
        {"planned_projects": len(planned), "run_projects": len(run_projects)},
    )


def selected_manifest_items(plan):
    items = []
    manifest = as_list(as_dict(plan).get("input_manifest"))
    items.extend(item for item in manifest if isinstance(item, dict))
    for _project, item in iter_selected_inputs(plan):
        if isinstance(item, dict):
            items.append(item)
    return items


def check_no_full_dump(data):
    failures = []
    warnings = []
    plan = review_plan(data)
    has_work = bool(selected_projects(plan))
    manifest = as_dict(plan).get("input_manifest")
    if has_work and not isinstance(manifest, list):
        failures.append("review plan missing input_manifest")
    items = selected_manifest_items(plan)
    if has_work and not items:
        failures.append("review plan has no scoped selected inputs")
    for idx, item in enumerate(items):
        context = f"input_manifest[{idx}]"
        item_type = text_value(item.get("type")).lower()
        reason = text_value(item.get("reason"))
        identity = text_value(item.get("id_or_path") or item.get("path") or item.get("relative_path"))
        if item_type in {"backup_dir", "full_backup", "archive", "folder_dump", "unscoped_dump"}:
            failures.append(f"{context} has unscoped dump type: {item_type}")
        if re.search(r"(?i)\b(zip|tar|archive|entire backup|full backup|whole backup|all markdowns)\b", identity):
            failures.append(f"{context} appears to reference an archive/full backup dump")
        if not identity:
            failures.append(f"{context} missing id_or_path/path/relative_path")
        if not reason:
            failures.append(f"{context} missing selection reason")
    return result("no_full_dump", failures, warnings, {"inputs": len(items)})


def check_token_estimate(data):
    failures = []
    warnings = []
    plan = review_plan(data)
    for project in selected_projects(plan):
        project_name = project.get("name") or "(unknown project)"
        selected = [item for item in as_list(project.get("selected_inputs")) if isinstance(item, dict)]
        estimate_obj = as_dict(project.get("estimate"))
        input_tokens = estimate_obj.get("input_tokens")
        total_tokens = estimate_obj.get("total_tokens")
        if not isinstance(input_tokens, int) or input_tokens < 0:
            failures.append(f"{project_name} missing nonnegative estimate.input_tokens")
            continue
        if not isinstance(total_tokens, int) or total_tokens < input_tokens:
            failures.append(f"{project_name} missing valid estimate.total_tokens")
        selected_tokens = 0
        for idx, item in enumerate(selected):
            tokens = item.get("estimated_input_tokens")
            if not isinstance(tokens, int) or tokens < 0:
                failures.append(f"{project_name}.selected_inputs[{idx}] missing nonnegative estimated_input_tokens")
            else:
                selected_tokens += tokens
        if selected and input_tokens < selected_tokens:
            failures.append(
                f"{project_name} estimate.input_tokens is lower than selected input token sum"
            )
        if selected and input_tokens > selected_tokens * 3 + 1000:
            warnings.append(f"{project_name} estimate.input_tokens is much larger than selected input token sum")
    return result("token_estimate", failures, warnings)


def check_evidence_grounding(data):
    failures = []
    warnings = []
    summaries = as_dict(as_dict(data.get(CONVERSATION_SUMMARIES_FILE)).get("conversations"))
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))

    for sid, entry in summaries.items():
        if not isinstance(entry, dict):
            continue
        refs = entry.get("evidence_refs")
        validate_evidence_refs(
            refs,
            f"conversation summary {sid}",
            failures,
            allowed_types={"conversation", "tool", "instruction_context"},
            require_content_hash=True,
        )
        expected_hash = text_value(entry.get("content_hash"))
        if expected_hash and isinstance(refs, list):
            if not any(isinstance(ref, dict) and text_value(ref.get("content_hash")) == expected_hash for ref in refs):
                failures.append(f"conversation summary {sid} evidence_refs do not include its content_hash")

    for project_name, review in reviews.items():
        if not isinstance(review, dict):
            continue
        validate_evidence_refs(review.get("evidence_refs"), f"{project_name} project review", failures)
        validate_evidence_refs(review.get("summary_evidence_refs"), f"{project_name}.summary", failures)
        if text_value(review.get("standing_context")):
            validate_evidence_refs(
                review.get("standing_context_evidence_refs"),
                f"{project_name}.standing_context",
                failures,
            )
        validate_evidence_refs(review.get("next_step_evidence_refs"), f"{project_name}.next_step", failures)
        validate_evidence_refs(review.get("roadmap_status_evidence_refs"), f"{project_name}.roadmap_status", failures)

        for idx, question in enumerate(as_list(review.get("open_questions"))):
            context = f"{project_name}.open_questions[{idx}]"
            if not isinstance(question, dict):
                failures.append(f"{context} must be an object with question/text and evidence_refs")
                continue
            if not text_value(question.get("question") or question.get("text")):
                failures.append(f"{context} missing question/text")
            validate_evidence_refs(question.get("evidence_refs"), context, failures)

        for idx, task in enumerate(as_list(review.get("tasks"))):
            context = f"{project_name}.tasks[{idx}]"
            if not isinstance(task, dict):
                continue
            task_id = text_value(task.get("id")) or str(idx)
            source = text_value(task.get("source"))
            if source not in TASK_SOURCES:
                failures.append(f"{context} {task_id} has invalid source: {source or '(missing)'}")
            validate_evidence_refs(task.get("evidence_refs"), f"{context} {task_id}", failures)
            if source == "inferred":
                if text_value(task.get("confidence")) not in CONFIDENCE_LEVELS:
                    failures.append(f"{context} {task_id} inferred task missing confidence")
                if not text_value(task.get("reason")):
                    failures.append(f"{context} {task_id} inferred task missing reason")

        for idx, update in enumerate(as_list(review.get("recommended_repo_doc_updates"))):
            context = f"{project_name}.recommended_repo_doc_updates[{idx}]"
            if not isinstance(update, dict):
                continue
            validate_evidence_refs(update.get("evidence_refs"), context, failures)

    return result(
        "evidence_grounding",
        failures,
        warnings,
        {"conversation_summaries": len(summaries), "project_reviews": len(reviews)},
    )


def check_tool_evidence_policy(data):
    failures = []
    warnings = []
    summaries = as_dict(as_dict(data.get(CONVERSATION_SUMMARIES_FILE)).get("conversations"))
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))

    for sid, entry in summaries.items():
        if not isinstance(entry, dict):
            continue
        summary = text_value(entry.get("summary"))
        if RAW_TOOL_OUTPUT_RE.search(summary):
            failures.append(f"conversation summary {sid} includes raw tool output instead of a summary")
        evidence_text = " ".join(
            [summary]
            + [text_value(value) for value in as_list(entry.get("decisions"))]
            + [text_value(value) for value in as_list(entry.get("blockers"))]
        )
        append_tool_policy_failure(failures, f"conversation summary {sid}", entry.get("evidence_refs"), evidence_text)

    project_field_refs = {
        "summary": "summary_evidence_refs",
        "standing_context": "standing_context_evidence_refs",
        "next_step": "next_step_evidence_refs",
        "roadmap_status": "roadmap_status_evidence_refs",
    }
    for project_name, review in reviews.items():
        if not isinstance(review, dict):
            continue
        for field, refs_field in project_field_refs.items():
            text = text_value(review.get(field))
            if RAW_TOOL_OUTPUT_RE.search(text):
                failures.append(f"{project_name}.{field} includes raw tool output")
            append_tool_policy_failure(
                failures,
                f"{project_name}.{field}",
                review.get(refs_field) or review.get("evidence_refs"),
                text,
            )
        for idx, task in enumerate(as_list(review.get("tasks"))):
            if not isinstance(task, dict):
                continue
            task_id = text_value(task.get("id")) or str(idx)
            task_text = " ".join([text_value(task.get(key)) for key in ("title", "task", "text", "summary")])
            status = text_value(task.get("status")).lower()
            if status in {"done", "closed", "complete", "completed"} and not has_tool_evidence(task.get("evidence_refs")):
                failures.append(f"{project_name}.tasks[{idx}] {task_id} is {status} without tool evidence")
            append_tool_policy_failure(failures, f"{project_name}.tasks[{idx}] {task_id}", task.get("evidence_refs"), task_text)

    return result(
        "tool_evidence_policy",
        failures,
        warnings,
        {"conversation_summaries": len(summaries), "project_reviews": len(reviews)},
    )


def check_instruction_context_policy(data):
    failures = []
    warnings = []
    summaries = as_dict(as_dict(data.get(CONVERSATION_SUMMARIES_FILE)).get("conversations"))
    reviews = as_dict(as_dict(data.get(PROJECT_REVIEWS_FILE)).get("projects"))

    for sid, entry in summaries.items():
        if not isinstance(entry, dict):
            continue
        append_instruction_text_failure(failures, f"conversation summary {sid}", entry.get("summary"))
        for field in ("decisions", "blockers", "task_hints"):
            for idx, value in enumerate(as_list(entry.get(field))):
                append_instruction_text_failure(failures, f"conversation summary {sid}.{field}[{idx}]", value)

    project_fields = {
        "summary": "summary_evidence_refs",
        "next_step": "next_step_evidence_refs",
        "roadmap_status": "roadmap_status_evidence_refs",
    }
    for project_name, review in reviews.items():
        if not isinstance(review, dict):
            continue
        for field, refs_field in project_fields.items():
            append_instruction_text_failure(failures, f"{project_name}.{field}", review.get(field))
            append_instruction_ref_failure(failures, f"{project_name}.{field}", review.get(refs_field))

        for idx, question in enumerate(as_list(review.get("open_questions"))):
            if not isinstance(question, dict):
                continue
            text = text_value(question.get("question") or question.get("text"))
            append_instruction_text_failure(failures, f"{project_name}.open_questions[{idx}]", text)
            append_instruction_ref_failure(failures, f"{project_name}.open_questions[{idx}]", question.get("evidence_refs"))

        for idx, task in enumerate(as_list(review.get("tasks"))):
            if not isinstance(task, dict):
                continue
            task_id = text_value(task.get("id")) or str(idx)
            task_text = " ".join([text_value(task.get(key)) for key in ("title", "task", "text", "summary")])
            append_instruction_text_failure(failures, f"{project_name}.tasks[{idx}] {task_id}", task_text)
            append_instruction_ref_failure(failures, f"{project_name}.tasks[{idx}] {task_id}", task.get("evidence_refs"))

        for idx, update in enumerate(as_list(review.get("recommended_repo_doc_updates"))):
            if not isinstance(update, dict):
                continue
            update_text = " ".join([text_value(update.get(key)) for key in ("reason", "action")])
            append_instruction_text_failure(failures, f"{project_name}.recommended_repo_doc_updates[{idx}]", update_text)
            append_instruction_ref_failure(
                failures,
                f"{project_name}.recommended_repo_doc_updates[{idx}]",
                update.get("evidence_refs"),
            )

        prompt = review.get("suggested_next_prompt")
        append_instruction_text_failure(failures, f"{project_name}.suggested_next_prompt", prompt)

    return result(
        "instruction_context_policy",
        failures,
        warnings,
        {"conversation_summaries": len(summaries), "project_reviews": len(reviews)},
    )


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
        if prompt and PROMPT_BOILERPLATE_RE.search(prompt):
            failures.append(f"{project_name} suggested_next_prompt is boilerplate")
        if prompt and not PROMPT_TARGET_RE.search(prompt):
            failures.append(f"{project_name} suggested_next_prompt must name a concrete file, section, view, component, or flow")
        if prompt and not PROMPT_VERIFY_RE.search(prompt):
            failures.append(f"{project_name} suggested_next_prompt must include a verification step")
        if prompt and not PROMPT_OUTPUT_RE.search(prompt):
            failures.append(f"{project_name} suggested_next_prompt must state the expected output or update")
    return result("actionability", failures, warnings)


def int_value(value):
    try:
        return int(value)
    except Exception:
        return 0


def check_semantic_quality_review(data):
    failures = []
    warnings = []
    latest = latest_update_run(data.get(UPDATE_LOG_FILE))
    if not latest:
        return result("semantic_quality_review", failures, warnings)
    latest = as_dict(latest)
    summary_count = int_value(
        latest.get("conversation_summaries")
        or latest.get("summaries")
        or latest.get("conversations_summarized")
    )
    if summary_count < SEMANTIC_SAMPLE_EVERY:
        return result("semantic_quality_review", failures, warnings, {"conversation_summaries": summary_count})

    review = as_dict(latest.get("semantic_quality_review"))
    if not review:
        failures.append("large generated-summary run missing semantic_quality_review metadata")
        return result("semantic_quality_review", failures, warnings, {"conversation_summaries": summary_count})

    status = str(review.get("status") or "").strip().lower()
    if status not in SEMANTIC_QUALITY_STATUSES:
        failures.append(f"semantic_quality_review has invalid status: {status or '(missing)'}")
    sample_every = int_value(review.get("sample_every"))
    if sample_every <= 0 or sample_every > SEMANTIC_SAMPLE_EVERY:
        failures.append(f"semantic_quality_review.sample_every must be between 1 and {SEMANTIC_SAMPLE_EVERY}")
    sampled = int_value(review.get("sampled_summaries"))
    always_reviewed = int_value(review.get("always_reviewed_summaries"))
    if status != "skipped" and sampled + always_reviewed <= 0:
        failures.append("semantic_quality_review did not record any sampled summaries")
    if status == "skipped":
        if not text_value(review.get("reason")):
            failures.append("semantic_quality_review skipped without a reason")
        if str(latest.get("status") or "").lower() == "ok":
            failures.append("semantic_quality_review was skipped but latest run is marked ok; use needs_attention")
    semantic_failures = as_list(review.get("failures"))
    if semantic_failures and str(latest.get("status") or "").lower() == "ok":
        failures.append("semantic_quality_review has failures but latest run is marked ok")
    if status == "needs_attention" and not as_list(review.get("warnings")) and not semantic_failures:
        warnings.append("semantic_quality_review needs_attention without warnings or failures")
    return result(
        "semantic_quality_review",
        failures,
        warnings,
        {
            "conversation_summaries": summary_count,
            "sampled_summaries": sampled,
            "always_reviewed_summaries": always_reviewed,
        },
    )


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
        check_conversation_summary_quality(data),
        check_project_review_quality(data),
        check_checkpoint_integrity(data),
        check_task_stability(data),
        check_privacy(data),
        check_source_precedence(data),
        check_incrementality(data),
        check_no_full_dump(data),
        check_token_estimate(data),
        check_evidence_grounding(data),
        check_tool_evidence_policy(data),
        check_instruction_context_policy(data),
        check_repo_sync_reflection(data),
        check_actionability(data),
        check_semantic_quality_review(data),
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
