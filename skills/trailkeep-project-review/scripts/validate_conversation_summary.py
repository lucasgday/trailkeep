#!/usr/bin/env python3
"""Validate one generated conversation summary before checkpointing it.

This is a deterministic, local pre-merge guard for the optional coding-agent
review layer. It makes the per-summary quality policy executable without
waiting for the full generated-output finalizer.

Usage:
  validate_conversation_summary.py --summary-json summary.json
  validate_conversation_summary.py --summary-json - --session-id session-1
"""
import argparse
import json
import re
import sys


SUMMARY_QUALITY_VERSION = "actionable-v3"
SUMMARY_SIGNAL_LEVELS = {
    "administrative",
    "low_signal",
    "context_dependent",
    "decision",
    "implementation",
    "blocker",
}
LOW_SIGNAL_LEVELS = {"administrative", "low_signal", "context_dependent"}
MATRIX_FIELDS = [
    "user_intents",
    "implemented_changes",
    "verification",
    "task_candidates",
    "ignored_or_low_signal",
]
COVERAGE_STATUSES = {"complete", "partial", "low_signal", "context_dependent", "unknown"}
VERIFICATION_STATUSES = {"passed", "failed", "not_run", "manual", "blocked", "unknown"}
TASK_CANDIDATE_STATUSES = {"candidate", "todo", "blocked", "discarded", "unknown"}
FILE_AREA_ROLES = {
    "mentioned",
    "discussed",
    "reviewed",
    "changed",
    "created",
    "removed",
    "tested",
    "configured",
    "designed",
    "blocked",
    "unknown",
}
MAX_EVIDENCE_QUOTE_CHARS = 280
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
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
PENDING_RE = re.compile(r"(?i)\b(follow[- ]?up|pending|todo|later|next step|pendiente|pr[oó]ximo paso)\b")


def load_json_arg(value):
    if value == "-":
        return json.load(sys.stdin)
    with open(value, encoding="utf-8") as f:
        return json.load(f)


def as_list(value):
    return value if isinstance(value, list) else []


def text_value(value):
    if value is None:
        return ""
    return str(value).strip()


def iter_strings(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)
    elif isinstance(value, str):
        yield value


def has_secret(value):
    return any(pattern.search(text) for text in iter_strings(value) for pattern in SECRET_PATTERNS)


def has_tool_evidence(entry):
    return any(
        isinstance(ref, dict) and text_value(ref.get("type")) == "tool"
        for ref in as_list(entry.get("evidence_refs"))
    )


def has_tool_ref(refs):
    return any(isinstance(ref, dict) and text_value(ref.get("type")) == "tool" for ref in as_list(refs))


def evidence_ref_target(ref):
    if not isinstance(ref, dict):
        return ""
    for key in ("id_or_path", "relative_path", "path", "session_id", "tool_name", "command", "status"):
        value = text_value(ref.get(key))
        if value:
            return value
    return ""


def validate_file_area_evidence_refs(refs, context, failures):
    if not isinstance(refs, list) or not refs:
        failures.append(f"{context} missing evidence_refs")
        return
    for idx, ref in enumerate(refs):
        label = f"{context}.evidence_refs[{idx}]"
        if not isinstance(ref, dict):
            failures.append(f"{label} must be an object")
            continue
        ref_type = text_value(ref.get("type"))
        if ref_type not in {"conversation", "tool"}:
            failures.append(f"{label}.type must be conversation or tool")
        if not evidence_ref_target(ref):
            failures.append(f"{label} must identify the source conversation or tool evidence")
        if not text_value(ref.get("content_hash")):
            failures.append(f"{label} missing content_hash")
        quote = text_value(ref.get("quote"))
        if len(quote) > MAX_EVIDENCE_QUOTE_CHARS:
            failures.append(f"{label}.quote exceeds {MAX_EVIDENCE_QUOTE_CHARS} characters")
        if has_secret(ref):
            failures.append(f"{label} contains a secret-looking literal")


def matrix_item_text(item):
    if not isinstance(item, dict):
        return text_value(item)
    for key in ("text", "intent", "change", "result", "task", "title", "reason", "summary", "question"):
        value = text_value(item.get(key))
        if value:
            return value
    return ""


def validate_matrix_items(entry, field, failures, *, require_tool=False):
    for idx, item in enumerate(as_list(entry.get(field))):
        label = f"{field}[{idx}]"
        if not isinstance(item, dict):
            failures.append(f"{label} must be an object with text and evidence_refs")
            continue
        if not matrix_item_text(item):
            failures.append(f"{label} missing readable text")
        validate_file_area_evidence_refs(item.get("evidence_refs"), label, failures)
        if require_tool and not has_tool_ref(item.get("evidence_refs")):
            failures.append(f"{label} claims implementation/verification without tool evidence")
        if field == "verification":
            status = text_value(item.get("status"))
            if status not in VERIFICATION_STATUSES:
                failures.append(f"{label}.status is missing or invalid")
            if status in {"passed", "failed"} and not has_tool_ref(item.get("evidence_refs")):
                failures.append(f"{label} status {status} requires tool evidence")
        if field == "task_candidates":
            candidate_id = text_value(item.get("id"))
            if not candidate_id:
                failures.append(f"{label}.id is required for rollup traceability")
            status = text_value(item.get("status"))
            if status not in TASK_CANDIDATE_STATUSES:
                failures.append(f"{label}.status is missing or invalid")


def validate_coverage_check(entry, failures, warnings):
    coverage = entry.get("coverage_check")
    if not isinstance(coverage, dict):
        failures.append("coverage_check must be an object")
        return
    status = text_value(coverage.get("status"))
    if status not in COVERAGE_STATUSES:
        failures.append("coverage_check.status is missing or invalid")
    uncovered = as_list(coverage.get("uncovered_items"))
    discarded = as_list(coverage.get("discarded_items"))
    if status == "complete" and uncovered:
        failures.append("coverage_check is complete but has uncovered_items")
    if status == "partial" and not uncovered:
        warnings.append("coverage_check is partial without uncovered_items")
    for key in ("covered_items", "uncovered_items", "discarded_items"):
        if key in coverage and not isinstance(coverage.get(key), list):
            failures.append(f"coverage_check.{key} must be a list")
    for idx, item in enumerate(discarded):
        if isinstance(item, dict) and not text_value(item.get("reason")):
            failures.append(f"coverage_check.discarded_items[{idx}] missing reason")


def validate_files_or_areas(entry, failures):
    for idx, item in enumerate(as_list(entry.get("files_or_areas"))):
        label = f"files_or_areas[{idx}]"
        if not isinstance(item, dict):
            failures.append(f"{label} must be an object with path or area, role, and evidence_refs")
            continue
        if not text_value(item.get("path")) and not text_value(item.get("area")):
            failures.append(f"{label} must include path or area")
        role = text_value(item.get("role"))
        if role not in FILE_AREA_ROLES:
            failures.append(f"{label}.role is missing or invalid")
        validate_file_area_evidence_refs(item.get("evidence_refs"), label, failures)


def validate_evidence_refs(entry, failures):
    refs = entry.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        failures.append("evidence_refs must include at least one conversation reference")
        return
    content_hash = text_value(entry.get("content_hash"))
    found_matching_hash = False
    for idx, ref in enumerate(refs):
        label = f"evidence_refs[{idx}]"
        if not isinstance(ref, dict):
            failures.append(f"{label} must be an object")
            continue
        ref_type = text_value(ref.get("type"))
        if ref_type not in {"conversation", "tool", "instruction_context"}:
            failures.append(f"{label}.type must be conversation, tool, or instruction_context")
        if not text_value(ref.get("id_or_path") or ref.get("path") or ref.get("session_id") or ref.get("tool_name") or ref.get("command") or ref.get("status")):
            failures.append(f"{label} must identify the source conversation or tool evidence")
        ref_hash = text_value(ref.get("content_hash"))
        if not ref_hash:
            failures.append(f"{label} missing content_hash")
        if ref_type == "conversation" and content_hash and ref_hash == content_hash:
            found_matching_hash = True
        quote = text_value(ref.get("quote"))
        if len(quote) > MAX_EVIDENCE_QUOTE_CHARS:
            failures.append(f"{label}.quote exceeds {MAX_EVIDENCE_QUOTE_CHARS} characters")
        if has_secret(ref):
            failures.append(f"{label} contains a secret-looking literal")
    if content_hash and not found_matching_hash:
        failures.append("evidence_refs do not include the summary content_hash")


def unwrap_entry(doc, session_id):
    if not isinstance(doc, dict):
        return None
    if "summary" in doc:
        return doc
    conversations = doc.get("conversations")
    if isinstance(conversations, dict):
        if session_id and session_id in conversations:
            return conversations[session_id]
        if len(conversations) == 1:
            return next(iter(conversations.values()))
    if session_id and session_id in doc and isinstance(doc[session_id], dict):
        return doc[session_id]
    if len(doc) == 1:
        only = next(iter(doc.values()))
        if isinstance(only, dict):
            return only
    return None


def validate(entry, expected_hash=None):
    failures = []
    warnings = []
    if not isinstance(entry, dict):
        return ["summary payload must be an object"], warnings

    required = [
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
    ]
    for key in required:
        if key not in entry:
            failures.append(f"missing field: {key}")

    for key in ["decisions", "blockers", "task_hints", "files_or_areas", *MATRIX_FIELDS]:
        if key in entry and not isinstance(entry.get(key), list):
            failures.append(f"{key} must be a list")
    for key in MATRIX_FIELDS:
        if key not in entry:
            failures.append(f"missing field: {key}")
    if "coverage_check" not in entry:
        failures.append("missing field: coverage_check")
    if as_list(entry.get("task_hints")):
        failures.append("task_hints is legacy; use task_candidates for actionable-v3 summaries")
    validate_files_or_areas(entry, failures)
    for field in ("user_intents", "task_candidates", "ignored_or_low_signal"):
        validate_matrix_items(entry, field, failures)
    validate_matrix_items(entry, "implemented_changes", failures, require_tool=True)
    validate_matrix_items(entry, "verification", failures)
    validate_coverage_check(entry, failures, warnings)

    if expected_hash and entry.get("content_hash") != expected_hash:
        failures.append("content_hash does not match expected hash")

    validate_evidence_refs(entry, failures)

    if entry.get("summary_quality_version") != SUMMARY_QUALITY_VERSION:
        failures.append("summary_quality_version is missing or stale")

    signal = str(entry.get("signal_level") or "").strip()
    if signal not in SUMMARY_SIGNAL_LEVELS:
        failures.append("signal_level is missing or invalid")

    include = entry.get("include_in_project_rollup")
    if not isinstance(include, bool):
        failures.append("include_in_project_rollup must be a boolean")
    elif include is False and not text_value(entry.get("not_rollup_reason")):
        failures.append("summary excluded from rollup must include not_rollup_reason")

    summary = entry.get("summary")
    if not isinstance(summary, str):
        failures.append("summary must be a string")
        summary = ""
    summary = summary.strip()
    if not summary:
        failures.append("summary is empty")

    if has_secret(entry):
        failures.append("summary contains a secret-looking literal")
    if SUMMARY_BOILERPLATE_RE.search(summary):
        failures.append("summary contains bootstrap/boilerplate text")
    if INSTRUCTION_CONTEXT_POLLUTION_RE.search(summary):
        failures.append("summary treats instruction/header context as conversation content")
    if ROLE_MARKER_POLLUTION_RE.search(summary):
        failures.append("summary contains role-marker pollution")
    if SUMMARY_SERIALIZED_OBJECT_RE.search(summary):
        failures.append("summary looks like a serialized object, not readable prose")
    if RAW_TOOL_OUTPUT_RE.search(summary):
        failures.append("summary includes raw tool output or code fence")

    execution_text = " ".join(
        [summary]
        + [text_value(value) for value in as_list(entry.get("decisions"))]
        + [text_value(value) for value in as_list(entry.get("blockers"))]
    )
    if TOOL_EVIDENCE_CLAIM_RE.search(execution_text) and not has_tool_evidence(entry):
        failures.append("execution or verification claims require tool evidence_refs")

    decisions = as_list(entry.get("decisions"))
    blockers = as_list(entry.get("blockers"))
    task_candidates = as_list(entry.get("task_candidates"))
    implemented_changes = as_list(entry.get("implemented_changes"))
    verification = as_list(entry.get("verification"))
    user_intents = as_list(entry.get("user_intents"))
    for label, values in [("decisions", decisions), ("blockers", blockers), ("task_candidates", task_candidates)]:
        if any(INSTRUCTION_CONTEXT_POLLUTION_RE.search(text_value(value)) for value in values):
            failures.append(f"{label} contains instruction/header context")
    if signal in LOW_SIGNAL_LEVELS:
        if include is True:
            failures.append("low-signal summary must not be included in project rollup")
        if decisions or blockers or task_candidates or implemented_changes or verification or user_intents:
            failures.append("low-signal summary must not invent intents, changes, verification, decisions, blockers, or task candidates")
        if not as_list(entry.get("ignored_or_low_signal")):
            failures.append("low-signal summary must explain ignored_or_low_signal")
    elif include is False:
        warnings.append("durable-signal summary is excluded from project rollup")
    else:
        if not user_intents:
            failures.append("durable-signal summary missing user_intents")
        if not verification:
            failures.append("durable-signal summary missing verification; record not_run if no check ran")
        if signal == "implementation" and not implemented_changes:
            failures.append("implementation summary missing implemented_changes")
        if signal == "decision" and not decisions:
            failures.append("decision summary missing decisions")
        if signal == "blocker" and not blockers:
            failures.append("blocker summary missing blockers")
    if PENDING_RE.search(summary) and not task_candidates and not blockers:
        failures.append("summary mentions pending/follow-up work but has no task_candidates or blockers")

    if signal in {"decision", "implementation", "blocker"} and len(summary) < 40:
        warnings.append("durable-signal summary is very short")

    return failures, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-json", required=True, help="Path to one summary JSON object, '-' for stdin, or a sidecar-shaped JSON object.")
    parser.add_argument("--session-id", default="", help="Session id to select when the input is sidecar-shaped.")
    parser.add_argument("--expected-content-hash", default="", help="Expected source content hash.")
    args = parser.parse_args()

    doc = load_json_arg(args.summary_json)
    entry = unwrap_entry(doc, args.session_id)
    failures, warnings = validate(entry, args.expected_content_hash or None)
    report = {
        "status": "fail" if failures else "pass",
        "summary_quality_version": SUMMARY_QUALITY_VERSION,
        "failures": failures,
        "warnings": warnings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
