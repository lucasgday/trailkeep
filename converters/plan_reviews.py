#!/usr/bin/env python3
"""Deterministic review preflight plan for the optional generative layer.

Reads the local backup folder and writes `_review_run_plan.json` before any
coding-agent automation has a reason to call a model. No network, no LLM.

Usage: plan_reviews.py <backup_dir>
"""
import datetime
import glob
import hashlib
import json
import math
import os
import re
import sys


PLAN_VERSION = 1
ESTIMATOR = "chars_div_4"
PREPROCESSED_INPUTS_FILE = "_review_preprocessed_inputs.json"
OUTPUT_FILES = [
    "_conversation_summaries.json",
    "_project_reviews.json",
    "_agent_profile.json",
    "_review_repo_sync.json",
    "_review_update_log.json",
]
TRUTH_DOCS = [
    "ROADMAP.md",
    "BACKLOG.md",
    "TODO.md",
    "design.md",
    "issues.md",
    "ISSUES.md",
    "tasks.md",
    "TASKS.md",
    "AGENTS.md",
    "CLAUDE.md",
    os.path.join("docs", "product-progress.md"),
    os.path.join("docs", "project-progress.md"),
    os.path.join("docs", "agent-handoff.md"),
    os.path.join("docs", "design-patterns.md"),
    os.path.join("docs", "design.md"),
    os.path.join("docs", "issues.md"),
    os.path.join("docs", "backlog.md"),
    os.path.join(".github", "ISSUE_TEMPLATE", "config.yml"),
]
MODEL_TIERS = {
    "daily_project_update": "default",
    "bootstrap_project": "strong",
    "deep_project_review": "strong",
    "deep_design_review": "strong",
    "global_synthesis": "strong",
}
SECRET_PATTERNS = [
    ("openai_project_key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{16,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("credential_assignment", re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}")),
    ("email", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
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


def estimate(text):
    chars = len(text)
    words = len(re.findall(r"\S+", text))
    return {
        "chars": chars,
        "words": words,
        "estimated_input_tokens": int(math.ceil(chars / 4.0)),
    }


def content_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def possible_secret(text):
    return any(pattern.search(text or "") for _, pattern in SECRET_PATTERNS)


def redact_secrets(text):
    redacted = text or ""
    replacements = []
    for label, pattern in SECRET_PATTERNS:
        def replace(match):
            placeholder = f"[REDACTED_{label.upper()}_{len(replacements) + 1}]"
            replacements.append({
                "type": label,
                "placeholder": placeholder,
                "start": match.start(),
                "end": match.end(),
            })
            return placeholder
        redacted = pattern.sub(replace, redacted)
    return redacted, replacements


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
    title = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"^#\s+(.+)$", text, re.M)
    if m:
        title = m.group(1).strip()
    rel = os.path.relpath(path, backup_dir)
    return {
        "id": meta_value(body, "id") or rel,
        "project": meta_value(body, "project", "proyecto") or os.path.basename(os.path.dirname(path)) or "(no project)",
        "source": meta_value(body, "source", "fuente") or "",
        "date": meta_value(body, "date", "fecha") or "",
        "title": title,
        "path": rel,
        "hash": content_hash(text),
        "text": text,
        "estimate": estimate(text),
        "possible_secret": possible_secret(text),
    }


def markdown_sessions(backup_dir):
    sessions = []
    for path in sorted(glob.glob(os.path.join(backup_dir, "markdown-*", "**", "*.md"), recursive=True)):
        try:
            sessions.append(parse_markdown(path, backup_dir))
        except Exception:
            continue
    return sessions


def project_docs(project_meta):
    path = project_meta.get("path")
    if not path or not os.path.isdir(path):
        return []
    docs = []
    for rel in TRUTH_DOCS:
        full = os.path.join(path, rel)
        if not os.path.isfile(full):
            continue
        try:
            text = open(full, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        e = estimate(text)
        docs.append({
            "type": "repo_doc",
            "id_or_path": full,
            "relative_path": rel,
            "reason": "repo planning/design/context source of truth",
            **e,
            "content_hash": content_hash(text),
            "possible_secret": possible_secret(text),
            "_text": text,
        })
    return docs


def sidecar_input(name, data, reason, input_type="sidecar"):
    if data is None:
        return None
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return {
        "type": input_type,
        "id_or_path": name,
        "reason": reason,
        **estimate(text),
        "content_hash": content_hash(text),
        "possible_secret": False,
    }


def reviewed_sessions(review_entry):
    cp = (review_entry or {}).get("checkpoints") or {}
    rs = cp.get("reviewed_sessions") or {}
    return rs if isinstance(rs, dict) else {}


def reviewed_repo_docs(review_entry):
    cp = (review_entry or {}).get("checkpoints") or {}
    docs = cp.get("reviewed_repo_docs") or cp.get("repo_docs") or {}
    return docs if isinstance(docs, dict) else {}


def session_changed(session, reviewed):
    old = reviewed.get(session["id"])
    if isinstance(old, dict):
        return old.get("content_hash") != session["hash"]
    if isinstance(old, str):
        return old != session["hash"]
    return True


def repo_doc_changed(doc, reviewed):
    for key in [doc.get("id_or_path"), doc.get("relative_path")]:
        if not key:
            continue
        if key not in reviewed:
            continue
        old = reviewed.get(key)
        if isinstance(old, dict):
            return old.get("content_hash") != doc.get("content_hash")
        if isinstance(old, str):
            return old != doc.get("content_hash")
    return True


def design_doc(doc):
    rel = str(doc.get("relative_path") or doc.get("id_or_path") or "").lower()
    return rel == "design.md" or rel.endswith("/design.md") or "design-patterns" in rel


def sum_estimate(inputs):
    input_tokens = sum(int(i.get("estimated_input_tokens") or 0) for i in inputs)
    overhead = int(math.ceil(input_tokens * 0.12))
    expected_output = max(1200, min(8000, int(math.ceil(input_tokens * 0.25))))
    return {
        "input_tokens": input_tokens,
        "overhead_tokens": overhead,
        "expected_output_tokens": expected_output,
        "total_tokens": input_tokens + overhead + expected_output,
    }


def approval_input_ref(item):
    ref = {}
    for key in ["type", "id_or_path", "relative_path", "path", "reason", "estimated_input_tokens", "content_hash", "possible_secret"]:
        if key in item:
            ref[key] = item[key]
    return ref


def approval_reasons(inputs):
    secret_inputs = [approval_input_ref(i) for i in inputs if i.get("possible_secret")]
    reasons = []
    if secret_inputs:
        reasons.append({
            "code": "possible_secret",
            "message": "Selected input may contain secrets, credentials, tokens, email addresses, or other sensitive values.",
            "input_refs": secret_inputs,
        })
    return reasons


def public_item(item):
    return {k: v for k, v in item.items() if not k.startswith("_")}


def preprocessed_key(project, item):
    return "\x1f".join([
        str(project or ""),
        str(item.get("type") or ""),
        str(item.get("id_or_path") or item.get("path") or ""),
        str(item.get("content_hash") or ""),
    ])


def add_preprocessed_input(preprocessed, project, item, text, metadata=None):
    redacted, replacements = redact_secrets(text)
    if not replacements:
        return item
    key = preprocessed_key(project, item)
    redacted_hash = content_hash(redacted)
    redaction_types = sorted(set(r["type"] for r in replacements))
    preprocessed["inputs"][key] = {
        "project": project,
        "type": item.get("type") or "",
        "id_or_path": item.get("id_or_path") or item.get("path") or "",
        "path": item.get("path") or "",
        "relative_path": item.get("relative_path") or "",
        "title": item.get("title") or "",
        "source": (metadata or {}).get("source") or item.get("source") or "",
        "date": (metadata or {}).get("date") or item.get("date") or "",
        "original_content_hash": item.get("content_hash") or "",
        "redacted_content_hash": redacted_hash,
        "redaction_count": len(replacements),
        "redaction_types": redaction_types,
        "text": redacted,
    }
    redacted_estimate = estimate(redacted)
    updated = dict(item)
    updated.update(redacted_estimate)
    updated.update({
        "possible_secret": True,
        "preprocessed": True,
        "preprocessed_ref": f"{PREPROCESSED_INPUTS_FILE}#{key}",
        "preprocessed_input_key": key,
        "preprocessed_content_hash": redacted_hash,
        "redaction_count": len(replacements),
        "redaction_types": redaction_types,
        "source_chars": item.get("chars", 0),
        "source_words": item.get("words", 0),
        "source_estimated_input_tokens": item.get("estimated_input_tokens", 0),
    })
    return updated


def plan_project(name, project_meta, sessions, review_entry, summaries, bootstrap, preprocessed):
    reviewed = reviewed_sessions(review_entry)
    reviewed_docs = reviewed_repo_docs(review_entry)
    selected_sessions = []
    for s in sorted(sessions, key=lambda x: x.get("date") or "", reverse=True):
        if bootstrap or session_changed(s, reviewed):
            selected_sessions.append(s)

    docs = project_docs(project_meta)
    changed_docs = [d for d in docs if bootstrap or repo_doc_changed(d, reviewed_docs)]
    if not (bootstrap or selected_sessions or changed_docs):
        return None

    inputs = []
    for d in docs:
        item = public_item(d)
        if d.get("possible_secret"):
            item = add_preprocessed_input(preprocessed, name, item, d.get("_text") or "")
        inputs.append(item)

    for s in selected_sessions:
        item = {
            "type": "conversation",
            "id_or_path": s["id"],
            "path": s["path"],
            "title": s["title"],
            "reason": "new or changed conversation for this project",
            **s["estimate"],
            "content_hash": s["hash"],
            "possible_secret": s["possible_secret"],
        }
        if s["possible_secret"]:
            item = add_preprocessed_input(
                preprocessed,
                name,
                item,
                s["text"],
                {"source": s.get("source") or "", "date": s.get("date") or ""},
            )
        inputs.append(item)

    summary_inputs = []
    conv_summaries = (summaries or {}).get("conversations") or {}
    for s in sessions:
        summary = conv_summaries.get(s["id"])
        item = sidecar_input(
            f"_conversation_summaries.json:{s['id']}",
            summary,
            "existing conversation summary checkpoint",
            "conversation_summary",
        )
        if item:
            summary_inputs.append(item)
    inputs.extend(summary_inputs[:20])

    if review_entry:
        item = sidecar_input(
            f"_project_reviews.json:{name}",
            review_entry,
            "previous project review checkpoint",
            "project_review",
        )
        if item:
            inputs.append(item)

    if not inputs:
        return None

    estimate_obj = sum_estimate(inputs)
    mode_key = "bootstrap_project" if bootstrap else "daily_project_update"
    model_tier = MODEL_TIERS.get(mode_key, "default")
    has_secret = any(i.get("possible_secret") for i in inputs)
    unredacted_secret_inputs = [
        i for i in inputs
        if i.get("possible_secret") and not i.get("preprocessed_ref")
    ]
    requires_approval = bool(unredacted_secret_inputs)
    approval_reason_list = approval_reasons(unredacted_secret_inputs)
    if bootstrap:
        reason = "missing project review entry; bootstrap required"
    elif selected_sessions and changed_docs:
        reason = "new or changed conversations and repo docs detected"
    elif changed_docs:
        reason = "new or changed repo docs detected"
    else:
        reason = "new or changed conversations detected"

    return {
        "name": name,
        "reason": reason,
        "mode": mode_key,
        "status": project_meta.get("status"),
        "path": project_meta.get("path"),
        "selected_inputs": inputs,
        "changed_inputs": {
            "conversations": len(selected_sessions),
            "repo_docs": len(changed_docs),
        },
        "estimate": estimate_obj,
        "model_tier": model_tier,
        "remote_provider_possible": True,
        "requires_approval": requires_approval,
        "approval_reasons": approval_reason_list,
        "needs_deep_review": bootstrap,
        "needs_deep_design_review": bootstrap or any(design_doc(d) for d in changed_docs),
        "possible_secret": has_secret,
        "preprocessed_inputs_file": PREPROCESSED_INPUTS_FILE if has_secret else "",
        "output_files": OUTPUT_FILES,
    }


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    backup_dir = sys.argv[1]
    projects_doc = load_json(os.path.join(backup_dir, "_projects.json"), {})
    reviews_doc = load_json(os.path.join(backup_dir, "_project_reviews.json"), {})
    summaries_doc = load_json(os.path.join(backup_dir, "_conversation_summaries.json"), {})
    project_meta = projects_doc.get("projects") or {}
    project_reviews = reviews_doc.get("projects") or {}
    sessions_by_project = {}
    for s in markdown_sessions(backup_dir):
        sessions_by_project.setdefault(s["project"], []).append(s)

    all_names = sorted(set(project_meta) | set(sessions_by_project))
    bootstrap_mode = not bool(project_reviews)
    generated_at = datetime.datetime.now().astimezone().isoformat()
    preprocessed = {
        "version": 1,
        "generated_at": generated_at,
        "source_plan_generated_at": generated_at,
        "inputs": {},
    }
    project_plans = []
    skipped = []
    for name in all_names:
        plan = plan_project(
            name,
            project_meta.get(name) or {},
            sessions_by_project.get(name) or [],
            project_reviews.get(name),
            summaries_doc,
            bootstrap_mode or name not in project_reviews,
            preprocessed,
        )
        if plan:
            project_plans.append(plan)
        else:
            skipped.append({"name": name, "reason": "no changed inputs detected"})

    input_manifest = []
    for p in project_plans:
        for item in p["selected_inputs"]:
            input_manifest.append({
                "project": p["name"],
                "type": item.get("type"),
                "id_or_path": item.get("id_or_path") or item.get("path"),
                "reason": item.get("reason"),
                "chars": item.get("chars", 0),
                "words": item.get("words", 0),
                "estimated_input_tokens": item.get("estimated_input_tokens", 0),
                "content_hash": item.get("content_hash"),
                "possible_secret": bool(item.get("possible_secret")),
                "preprocessed": bool(item.get("preprocessed")),
                "preprocessed_ref": item.get("preprocessed_ref") or "",
                "preprocessed_content_hash": item.get("preprocessed_content_hash") or "",
                "redaction_count": item.get("redaction_count", 0),
            })

    totals = sum_estimate(input_manifest)
    doc = {
        "version": PLAN_VERSION,
        "generated_at": generated_at,
        "mode": "bootstrap" if bootstrap_mode else "daily",
        "estimator": ESTIMATOR,
        "model_tiers": MODEL_TIERS,
        "preprocessed_inputs_file": PREPROCESSED_INPUTS_FILE,
        "input_manifest": input_manifest,
        "output_files": OUTPUT_FILES,
        "projects": project_plans,
        "skipped_projects": skipped,
        "totals": totals,
        "notes": [
            "Deterministic local preflight only. No model calls were made.",
            "The optional coding-agent skill should read this plan before sending context to any model provider.",
        ],
    }
    write_json(os.path.join(backup_dir, PREPROCESSED_INPUTS_FILE), preprocessed)
    out = os.path.join(backup_dir, "_review_run_plan.json")
    write_json(out, doc)
    approval = sum(1 for p in project_plans if p["requires_approval"])
    print(f"Review plan: {len(project_plans)} project(s), {totals['input_tokens']} input tokens estimated, {approval} flagged for approval")


if __name__ == "__main__":
    main()
