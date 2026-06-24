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


SUMMARY_QUALITY_VERSION = "actionable-v2"
SUMMARY_SIGNAL_LEVELS = {
    "administrative",
    "low_signal",
    "context_dependent",
    "decision",
    "implementation",
    "blocker",
}
LOW_SIGNAL_LEVELS = {"administrative", "low_signal", "context_dependent"}
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

    for key in ["decisions", "blockers", "task_hints", "files_or_areas"]:
        if key in entry and not isinstance(entry.get(key), list):
            failures.append(f"{key} must be a list")

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
    task_hints = as_list(entry.get("task_hints"))
    for label, values in [("decisions", decisions), ("blockers", blockers), ("task_hints", task_hints)]:
        if any(INSTRUCTION_CONTEXT_POLLUTION_RE.search(text_value(value)) for value in values):
            failures.append(f"{label} contains instruction/header context")
    if signal in LOW_SIGNAL_LEVELS:
        if include is True:
            failures.append("low-signal summary must not be included in project rollup")
        if decisions or blockers or task_hints:
            failures.append("low-signal summary must not invent decisions, blockers, or task hints")
    elif include is False:
        warnings.append("durable-signal summary is excluded from project rollup")

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
