#!/usr/bin/env python3
"""Deterministic evals for the optional review preflight plan.

Reads `_review_run_plan.json` and writes `_review_eval_report.json`.
No network, no LLM. These checks validate the local planner contract only;
generated sidecar evals run later through `eval_generated_reviews.py`.

Usage: eval_review_plan.py <backup_dir>
"""
import datetime
import json
import math
import os
import re
import sys


REPORT_VERSION = 1
PLAN_FILE = "_review_run_plan.json"
REPORT_FILE = "_review_eval_report.json"
PREPROCESSED_INPUTS_FILE = "_review_preprocessed_inputs.json"
ALLOWED_INPUT_TYPES = {
    "repo_doc",
    "conversation",
    "conversation_summary",
    "project_review",
    "sidecar",
}
ALLOWED_OUTPUT_FILES = {
    "_conversation_summaries.json",
    "_project_reviews.json",
    "_agent_profile.json",
    "_review_repo_sync.json",
    "_review_update_log.json",
}
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
]


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


def is_nonnegative_int(value):
    return isinstance(value, int) and value >= 0


def iter_project_inputs(plan):
    for project in plan.get("projects") or []:
        for item in project.get("selected_inputs") or []:
            yield project, item


def item_key(project_name, item):
    return (
        project_name,
        str(item.get("type") or ""),
        str(item.get("id_or_path") or item.get("path") or ""),
        str(item.get("content_hash") or ""),
    )


def expected_estimate(chars):
    return int(math.ceil((chars or 0) / 4.0))


def expected_total(items):
    input_tokens = sum(int(i.get("estimated_input_tokens") or 0) for i in items)
    overhead = int(math.ceil(input_tokens * 0.12))
    expected_output = max(1200, min(8000, int(math.ceil(input_tokens * 0.25))))
    return {
        "input_tokens": input_tokens,
        "overhead_tokens": overhead,
        "expected_output_tokens": expected_output,
        "total_tokens": input_tokens + overhead + expected_output,
    }


def check_schema(plan):
    failures = []
    required = [
        "version",
        "generated_at",
        "mode",
        "estimator",
        "model_tiers",
        "input_manifest",
        "output_files",
        "projects",
        "skipped_projects",
        "totals",
    ]
    for key in required:
        if key not in plan:
            failures.append(f"missing top-level field: {key}")
    if plan.get("version") != 1:
        failures.append("version must be 1")
    if not isinstance(plan.get("input_manifest"), list):
        failures.append("input_manifest must be a list")
    if not isinstance(plan.get("projects"), list):
        failures.append("projects must be a list")
    if not isinstance(plan.get("model_tiers"), dict):
        failures.append("model_tiers must be an object")

    for idx, project in enumerate(plan.get("projects") or []):
        prefix = f"projects[{idx}]"
        for key in [
            "name",
            "reason",
            "mode",
            "selected_inputs",
            "changed_inputs",
            "estimate",
            "model_tier",
            "remote_provider_possible",
            "requires_approval",
            "needs_deep_review",
            "needs_deep_design_review",
            "possible_secret",
            "output_files",
        ]:
            if key not in project:
                failures.append(f"{prefix} missing field: {key}")
        if not isinstance(project.get("selected_inputs"), list):
            failures.append(f"{prefix}.selected_inputs must be a list")
        if project.get("mode") not in (plan.get("model_tiers") or {}):
            failures.append(f"{prefix}.mode has no matching model_tiers entry")
        if project.get("model_tier") != (plan.get("model_tiers") or {}).get(project.get("mode")):
            failures.append(f"{prefix}.model_tier does not match model_tiers")
        if project.get("requires_approval"):
            reasons = project.get("approval_reasons")
            if not isinstance(reasons, list) or not reasons:
                failures.append(f"{prefix}.approval_reasons must explain why approval is required")
            for ridx, reason in enumerate(reasons or []):
                if not isinstance(reason, dict):
                    failures.append(f"{prefix}.approval_reasons[{ridx}] must be an object")
                    continue
                if not reason.get("code"):
                    failures.append(f"{prefix}.approval_reasons[{ridx}] missing code")
                if not isinstance(reason.get("input_refs"), list):
                    failures.append(f"{prefix}.approval_reasons[{ridx}].input_refs must be a list")

    for project, item in iter_project_inputs(plan):
        prefix = f"{project.get('name')}:input"
        for key in ["type", "id_or_path", "reason", "chars", "words", "estimated_input_tokens", "content_hash", "possible_secret"]:
            if key not in item:
                failures.append(f"{prefix} missing field: {key}")
        if item.get("type") not in ALLOWED_INPUT_TYPES:
            failures.append(f"{prefix} has unsupported type: {item.get('type')}")

    return result("schema", failures, stats={"projects": len(plan.get("projects") or [])})


def check_input_manifest(plan):
    failures = []
    manifest = plan.get("input_manifest") or []
    manifest_keys = {item_key(str(m.get("project") or ""), m) for m in manifest}
    selected_keys = {
        item_key(str(project.get("name") or ""), item)
        for project, item in iter_project_inputs(plan)
    }
    missing = selected_keys - manifest_keys
    extra = manifest_keys - selected_keys
    if missing:
        failures.append(f"{len(missing)} selected input(s) missing from input_manifest")
    if extra:
        failures.append(f"{len(extra)} manifest input(s) not present in selected_inputs")
    for idx, item in enumerate(manifest):
        for key in ["project", "type", "id_or_path", "reason", "chars", "words", "estimated_input_tokens", "content_hash", "possible_secret"]:
            if key not in item:
                failures.append(f"input_manifest[{idx}] missing field: {key}")
    return result("input_manifest", failures, stats={"manifest_inputs": len(manifest), "selected_inputs": len(selected_keys)})


def check_no_full_dump(plan, backup_dir):
    failures = []
    warnings = []
    backup_abs = os.path.abspath(backup_dir)
    banned_types = {"backup_folder", "raw_folder", "full_archive", "raw_transcript"}
    banned_keys = {"text", "raw", "transcript", "body", "content"}
    for project, item in iter_project_inputs(plan):
        name = project.get("name") or "(unknown project)"
        if item.get("type") in banned_types:
            failures.append(f"{name} selects banned input type {item.get('type')}")
        for key in item:
            if key in banned_keys:
                failures.append(f"{name} input includes raw-content key: {key}")
        path = str(item.get("id_or_path") or item.get("path") or "")
        if path in {"", ".", "./"}:
            failures.append(f"{name} has empty or root-like input path")
            continue
        if os.path.isabs(path):
            abs_path = os.path.abspath(path)
            if abs_path == backup_abs:
                failures.append(f"{name} selects the whole backup folder")
            if os.path.isdir(abs_path):
                failures.append(f"{name} selects a directory instead of a file/session id: {path}")
        if item.get("type") == "conversation" and not item.get("content_hash"):
            warnings.append(f"{name} conversation input has no content_hash")
    return result("no_full_dump", failures, warnings)


def check_privacy(plan, backup_dir):
    failures = []
    warnings = []
    dumped = json.dumps(plan, ensure_ascii=False)
    for pattern in SECRET_PATTERNS:
        if pattern.search(dumped):
            failures.append("plan contains a secret-looking literal instead of only possible_secret flags")
            break
    for project in plan.get("projects") or []:
        inputs = project.get("selected_inputs") or []
        has_secret = any(bool(i.get("possible_secret")) for i in inputs)
        unhandled = [
            i for i in inputs
            if i.get("possible_secret") and not i.get("preprocessed_ref") and not i.get("requires_approval")
        ]
        if has_secret and not project.get("possible_secret"):
            failures.append(f"{project.get('name')} has secret input but possible_secret=false")
        if unhandled and not project.get("requires_approval"):
            warnings.append(f"{project.get('name')} has secret input without preprocessed_ref; gate must auto-exclude it")
        if project.get("requires_approval") and not project.get("approval_reasons"):
            failures.append(f"{project.get('name')} has secret input but approval_reasons is empty")
        for item in inputs:
            if item.get("preprocessed_ref") and not item.get("preprocessed_content_hash"):
                failures.append(f"{project.get('name')} preprocessed input missing preprocessed_content_hash")
            if item.get("preprocessed_ref") and not item.get("redaction_count"):
                failures.append(f"{project.get('name')} preprocessed input missing redaction_count")

    preprocessed_path = os.path.join(backup_dir, str(plan.get("preprocessed_inputs_file") or PREPROCESSED_INPUTS_FILE))
    if os.path.exists(preprocessed_path):
        preprocessed = load_json(preprocessed_path, {})
        dumped_preprocessed = json.dumps(preprocessed, ensure_ascii=False)
        for pattern in SECRET_PATTERNS:
            if pattern.search(dumped_preprocessed):
                failures.append(f"{os.path.basename(preprocessed_path)} contains a secret-looking literal after redaction")
                break
    return result("privacy_basic", failures, warnings)


def check_token_estimates(plan):
    failures = []
    for project, item in iter_project_inputs(plan):
        chars = item.get("chars")
        words = item.get("words")
        tokens = item.get("estimated_input_tokens")
        if not (is_nonnegative_int(chars) and is_nonnegative_int(words) and is_nonnegative_int(tokens)):
            failures.append(f"{project.get('name')} input has invalid numeric estimate")
            continue
        expected = expected_estimate(chars)
        if tokens != expected:
            failures.append(f"{project.get('name')} input estimate {tokens} != ceil(chars/4) {expected}")

    for project in plan.get("projects") or []:
        expected = expected_total(project.get("selected_inputs") or [])
        if project.get("estimate") != expected:
            failures.append(f"{project.get('name')} project estimate does not match selected inputs")
    expected = expected_total(plan.get("input_manifest") or [])
    if plan.get("totals") != expected:
        failures.append("top-level totals do not match input_manifest")
    return result("token_estimate", failures)


def check_source_precedence(plan):
    failures = []
    warnings = []
    for project in plan.get("projects") or []:
        inputs = project.get("selected_inputs") or []
        first_conversation = None
        last_doc = None
        for idx, item in enumerate(inputs):
            if item.get("type") == "repo_doc":
                last_doc = idx
                if "source of truth" not in str(item.get("reason") or ""):
                    warnings.append(f"{project.get('name')} repo_doc reason does not mention source of truth")
            if item.get("type") == "conversation" and first_conversation is None:
                first_conversation = idx
        if first_conversation is not None and last_doc is not None and last_doc > first_conversation:
            failures.append(f"{project.get('name')} has repo_doc after conversation input")
    return result("source_precedence", failures, warnings)


def check_incrementality(plan):
    failures = []
    warnings = []
    project_names = {p.get("name") for p in plan.get("projects") or []}
    skipped_names = {p.get("name") for p in plan.get("skipped_projects") or []}
    overlap = project_names & skipped_names
    if overlap:
        failures.append(f"project(s) both planned and skipped: {', '.join(sorted(overlap))}")
    for project in plan.get("projects") or []:
        changed = project.get("changed_inputs") or {}
        if project.get("mode") == "daily_project_update":
            if not (changed.get("conversations") or changed.get("repo_docs")):
                failures.append(f"{project.get('name')} daily update has no changed inputs")
        if project.get("mode") == "bootstrap_project" and not project.get("needs_deep_review"):
            warnings.append(f"{project.get('name')} bootstrap project does not mark needs_deep_review")
    return result("incrementality", failures, warnings)


def check_output_scope(plan):
    failures = []
    all_outputs = list(plan.get("output_files") or [])
    for project in plan.get("projects") or []:
        all_outputs.extend(project.get("output_files") or [])
    for output in all_outputs:
        if output not in ALLOWED_OUTPUT_FILES:
            failures.append(f"unsupported output file: {output}")
        if os.path.isabs(str(output)) or "/" in str(output):
            failures.append(f"output file must be a local sidecar name, got: {output}")
    return result("output_scope", failures, stats={"output_files": sorted(set(all_outputs))})


def run_checks(plan, backup_dir):
    if not isinstance(plan, dict):
        return [result("schema", ["plan is missing or invalid JSON"])]
    return [
        check_schema(plan),
        check_input_manifest(plan),
        check_no_full_dump(plan, backup_dir),
        check_privacy(plan, backup_dir),
        check_token_estimates(plan),
        check_source_precedence(plan),
        check_incrementality(plan),
        check_output_scope(plan),
    ]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    backup_dir = sys.argv[1]
    plan_path = os.path.join(backup_dir, PLAN_FILE)
    report_path = os.path.join(backup_dir, REPORT_FILE)
    plan = load_json(plan_path, None)
    checks = run_checks(plan, backup_dir)
    failed = [c for c in checks if c["status"] == "fail"]
    warnings = sum(len(c.get("warnings") or []) for c in checks)
    report = {
        "version": REPORT_VERSION,
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "plan_path": PLAN_FILE,
        "plan_generated_at": plan.get("generated_at") if isinstance(plan, dict) else None,
        "scope": "deterministic_review_plan",
        "status": "fail" if failed else "pass",
        "checks": checks,
        "summary": {
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "failed": len(failed),
            "warnings": warnings,
        },
        "notes": [
            "No model calls were made.",
            "This report validates the deterministic planner only; generated sidecar evals run separately with eval_generated_reviews.py.",
        ],
    }
    write_json(report_path, report)
    print(f"Review plan eval: {report['status']} ({report['summary']['passed']} passed, {report['summary']['failed']} failed, {warnings} warnings)")
    if failed:
        for check in failed[:3]:
            print(f"  {check['name']}: {check['failures'][0]}")


if __name__ == "__main__":
    main()
