#!/usr/bin/env python3
"""Prepare an isolated project-scoped trailkeep review test folder.

This script copies only the deterministic sidecars and selected markdown files
needed to test one project's optional generative review flow. It never calls a
model and never writes to the source backup folder.
"""
import argparse
import copy
import datetime
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PLAN_FILE = "_review_run_plan.json"
PLAN_EVAL_FILE = "_review_eval_report.json"
PREPROCESSED_INPUTS_FILE = "_review_preprocessed_inputs.json"
PROJECTS_FILE = "_projects.json"
CONVERSATION_SUMMARIES_FILE = "_conversation_summaries.json"
PROJECT_REVIEWS_FILE = "_project_reviews.json"
AGENT_PROFILE_FILE = "_agent_profile.json"
REVIEW_UPDATE_LOG_FILE = "_review_update_log.json"
BACKUP_LOG_FILE = "log.json"
EFFECTIVE_PLAN_FILE = "_review_effective_plan.json"
SUMMARY_QUALITY_VERSION = "actionable-v3"


def now():
    return datetime.datetime.now().astimezone().isoformat()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def copy_if_exists(src, dst):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def slug(value):
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80] or "project"


def item_key(project_name, item):
    return "\x1f".join(
        [
            str(project_name or ""),
            str(item.get("type") or ""),
            str(item.get("id_or_path") or item.get("path") or ""),
            str(item.get("content_hash") or ""),
        ]
    )


def expected_total(items):
    input_tokens = sum(int(item.get("estimated_input_tokens") or 0) for item in items)
    overhead = int(math.ceil(input_tokens * 0.12))
    expected_output = max(1200, min(8000, int(math.ceil(input_tokens * 0.25))))
    return {
        "input_tokens": input_tokens,
        "overhead_tokens": overhead,
        "expected_output_tokens": expected_output,
        "total_tokens": input_tokens + overhead + expected_output,
    }


def plan_projects(plan):
    rows = plan.get("projects") if isinstance(plan, dict) else []
    return rows if isinstance(rows, list) else []


def find_project(plan, project_name):
    for project in plan_projects(plan):
        if isinstance(project, dict) and project.get("name") == project_name:
            return project
    return None


def scope_plan(plan, project_name):
    project = find_project(plan, project_name)
    if not project:
        available = ", ".join(
            sorted(str(p.get("name")) for p in plan_projects(plan) if isinstance(p, dict) and p.get("name"))
        )
        raise ValueError(f"project not found in review plan: {project_name}. Available: {available}")

    scoped = copy.deepcopy(plan)
    scoped_project = copy.deepcopy(project)
    selected = [item for item in scoped_project.get("selected_inputs") or [] if isinstance(item, dict)]
    selected_keys = {item_key(project_name, item) for item in selected}

    manifest = []
    for item in scoped.get("input_manifest") or []:
        if not isinstance(item, dict):
            continue
        if item.get("project") != project_name:
            continue
        if item_key(project_name, item) in selected_keys:
            manifest.append(copy.deepcopy(item))

    scoped_project["estimate"] = expected_total(selected)
    scoped["projects"] = [scoped_project]
    scoped["input_manifest"] = manifest
    scoped["totals"] = expected_total(manifest)
    scoped["test_scope"] = {
        "enabled": True,
        "project": project_name,
        "prepared_at": now(),
        "source": "project-scoped-review-test",
    }

    skipped = []
    seen = set()
    for project_row in plan_projects(plan):
        if not isinstance(project_row, dict):
            continue
        name = project_row.get("name")
        if not name or name == project_name or name in seen:
            continue
        skipped.append({"name": name, "reason": "excluded from project-scoped review test"})
        seen.add(name)
    for row in scoped.get("skipped_projects") or []:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name or name == project_name or name in seen:
            continue
        skipped.append(copy.deepcopy(row))
        seen.add(name)
    scoped["skipped_projects"] = skipped

    notes = list(scoped.get("notes") or [])
    notes.append(
        "Project-scoped test plan. It is intended for an isolated sandbox and must not be used as the global daily review plan."
    )
    scoped["notes"] = notes
    return scoped, scoped_project


def preprocessed_key(ref):
    text = str(ref or "")
    if "#" not in text:
        return ""
    return text.split("#", 1)[1]


def selected_preprocessed_keys(project):
    keys = set()
    for item in project.get("selected_inputs") or []:
        key = preprocessed_key(item.get("preprocessed_ref"))
        if key:
            keys.add(key)
    return keys


def filter_preprocessed(source_doc, scoped_project):
    inputs = source_doc.get("inputs") if isinstance(source_doc, dict) else {}
    if not isinstance(inputs, dict):
        inputs = {}
    keep = selected_preprocessed_keys(scoped_project)
    filtered = {key: value for key, value in inputs.items() if key in keep}
    return {
        "version": 1,
        "generated_at": source_doc.get("generated_at") if isinstance(source_doc, dict) else now(),
        "source_plan_generated_at": source_doc.get("source_plan_generated_at") if isinstance(source_doc, dict) else "",
        "inputs": filtered,
    }


def filter_projects_doc(source_doc, project_name):
    projects = source_doc.get("projects") if isinstance(source_doc, dict) else {}
    if isinstance(projects, dict):
        filtered = {project_name: projects[project_name]} if project_name in projects else {}
    elif isinstance(projects, list):
        filtered = [row for row in projects if isinstance(row, dict) and row.get("name") == project_name]
    else:
        filtered = {}
    return {
        "generated": source_doc.get("generated") if isinstance(source_doc, dict) else now(),
        "projects": filtered,
    }


def empty_conversation_summaries():
    return {
        "version": 1,
        "summary_quality_version": SUMMARY_QUALITY_VERSION,
        "conversations": {},
    }


def empty_project_reviews():
    return {
        "version": 1,
        "projects": {},
    }


def empty_agent_profile():
    return {
        "version": 1,
        "scope": "global",
        "recurring_preferences": [],
        "working_style": [],
        "repo_conventions": [],
        "prompting_patterns": [],
        "evidence": [],
    }


def filter_conversation_summaries(source_doc, project_name, selected_ids):
    if not isinstance(source_doc, dict):
        return empty_conversation_summaries()
    conversations = source_doc.get("conversations")
    if not isinstance(conversations, dict):
        return empty_conversation_summaries()
    filtered = {}
    for key, entry in conversations.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("project") == project_name or key in selected_ids:
            filtered[key] = entry
    out = dict(source_doc)
    out["version"] = 1
    out["conversations"] = filtered
    return out


def filter_project_reviews(source_doc, project_name):
    if not isinstance(source_doc, dict):
        return empty_project_reviews()
    projects = source_doc.get("projects")
    if not isinstance(projects, dict):
        return empty_project_reviews()
    out = dict(source_doc)
    out["version"] = 1
    out["projects"] = {project_name: projects[project_name]} if project_name in projects else {}
    return out


def link_or_copy(src, dst, copy_files):
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        return True
    if copy_files:
        shutil.copy2(src, dst)
    else:
        try:
            os.symlink(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return True


def selected_conversation_paths(project, source_backup_dir, sandbox_dir, copy_files):
    selected_ids = set()
    linked = []
    for item in project.get("selected_inputs") or []:
        if item.get("type") != "conversation":
            continue
        if item.get("id_or_path"):
            selected_ids.add(str(item.get("id_or_path")))
        rel = item.get("path")
        if not rel:
            continue
        src = source_backup_dir / rel
        dst = sandbox_dir / rel
        if link_or_copy(src, dst, copy_files):
            linked.append(dst)
    return selected_ids, linked


def format_tokens(value):
    value = int(value or 0)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1000:.1f}k"
    return str(value)


def render_test_prompt(args, sandbox_dir, project, linked_markdowns):
    review_gate_cmd = Path(args.trailkeep_repo) / "scripts" / "run-project-review-agent-gates.sh"
    quoted_gate_cmd = shlex.quote(str(review_gate_cmd))
    quoted_sandbox_dir = shlex.quote(str(sandbox_dir))
    output_language = args.output_language
    prompt_lines = [
        "Run a project-scoped trailkeep review test.",
        "",
        "Scope:",
        f"- project: {project.get('name')}",
        f"- backup_dir: {sandbox_dir}",
        f"- trailkeep_repo: {args.trailkeep_repo}",
        f"- output_language: \"{output_language}\"",
        "- this is an isolated test sandbox; do not write generated sidecars to the real backup folder",
        "",
        "Known facts:",
        f"- path: {project.get('path') or 'unknown'}",
        f"- status: {project.get('status') or 'unknown'}",
        f"- mode: {project.get('mode') or 'unknown'}",
        f"- model_tier: {project.get('model_tier') or 'unknown'}",
        f"- estimated input tokens: {format_tokens(project.get('estimate', {}).get('input_tokens'))}",
        f"- selected inputs: {len(project.get('selected_inputs') or [])}",
        f"- selected conversation files linked in sandbox: {len(linked_markdowns)}",
    ]

    prompt_lines.extend(
        [
            "",
            "Instructions:",
            "- Follow docs/generative-layer.md from the local trailkeep repo.",
            "- Follow skills/trailkeep-project-review/SKILL.md from the local trailkeep repo.",
            f"- Write all generated sidecar prose for this test in output_language: \"{output_language}\". Keep JSON schema keys in English.",
            f"- Use review_gate_cmd: {review_gate_cmd}",
            f"- Before any model call, run: {quoted_gate_cmd} pre --backup-dir {quoted_sandbox_dir}",
            "- Continue only if the pre gate exits 0. Use only _review_effective_plan.json from this sandbox.",
            f"- Before reviewing local git repos, run: {quoted_gate_cmd} repo-sync --backup-dir {quoted_sandbox_dir}",
            "- For selected inputs with preprocessed_ref, read sanitized text from this sandbox's _review_preprocessed_inputs.json instead of raw markdown.",
            "- Write generated sidecars only at this sandbox root: _conversation_summaries.json, _project_reviews.json, _agent_profile.json, _review_repo_sync.json, and _review_update_log.json.",
            "- Validate every conversation summary before merging it by running validate-summary through review_gate_cmd.",
            f"- After writing sidecars, run finalize through review_gate_cmd with the concrete model metadata and --output-language {output_language}.",
            "- If finalize fails, report the failure and do not mark this test ok.",
            "- Do not modify source markdown backups, project repos, or the real backup folder.",
            "",
            "Return a short report with:",
            "- sidecars written in the sandbox;",
            "- project review status;",
            "- generated-output eval result;",
            "- whether the output is good enough to rerun against the real backup folder.",
        ]
    )
    return "\n".join(prompt_lines) + "\n"


def render_instructions(args, sandbox_dir, prompt_path):
    review_gate_cmd = Path(args.trailkeep_repo) / "scripts" / "run-project-review-agent-gates.sh"
    quoted_gate_cmd = shlex.quote(str(review_gate_cmd))
    quoted_sandbox_dir = shlex.quote(str(sandbox_dir))
    return f"""# Trailkeep project review test sandbox

This folder is an isolated copy for one project. It is safe to let a coding
agent write generated review sidecars here first.

Source backup folder:
{args.backup_dir}

Sandbox backup_dir:
{sandbox_dir}

Prompt to paste:
{prompt_path}

Useful commands:

```sh
{quoted_gate_cmd} pre --backup-dir {quoted_sandbox_dir}
{quoted_gate_cmd} repo-sync --backup-dir {quoted_sandbox_dir}
{quoted_gate_cmd} finalize --backup-dir {quoted_sandbox_dir} --model-provider <provider> --model-routing <available|unavailable> --model-used <model>
```

If this test produces good sidecars, rerun the real review against the real
backup folder. Do not copy sandbox sidecars into the real backup folder unless
you intentionally want to promote that test output.
"""


def run_eval_and_gate(args, sandbox_dir):
    eval_script = Path(args.trailkeep_repo) / "converters" / "eval_review_plan.py"
    gate_script = Path(args.skill_dir) / "scripts" / "pre_model_gate.py"
    eval_proc = subprocess.run(
        [sys.executable, str(eval_script), str(sandbox_dir)],
        text=True,
        capture_output=True,
    )
    if eval_proc.returncode != 0:
        raise RuntimeError(eval_proc.stdout + eval_proc.stderr)
    gate_proc = subprocess.run(
        [
            sys.executable,
            str(gate_script),
            "--backup-dir",
            str(sandbox_dir),
            "--no-write-log",
        ],
        text=True,
        capture_output=True,
    )
    if gate_proc.returncode != 0:
        raise RuntimeError(gate_proc.stdout + gate_proc.stderr)
    return eval_proc.stdout.strip(), gate_proc.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--trailkeep-repo", required=True)
    parser.add_argument("--skill-dir", required=True)
    parser.add_argument("--output-dir", help="Optional destination folder. Defaults to a new /tmp folder.")
    parser.add_argument("--output-language", choices=("en", "es"), default="en", help="Language for generated sidecar prose in the test prompt. JSON schema keys remain English.")
    parser.add_argument("--copy-files", action="store_true", help="Copy selected markdown files instead of symlinking them.")
    parser.add_argument("--skip-gate", action="store_true", help="Prepare files without running planner eval/pre gate in the sandbox.")
    args = parser.parse_args()

    args.backup_dir = os.path.abspath(args.backup_dir)
    args.trailkeep_repo = os.path.abspath(args.trailkeep_repo)
    args.skill_dir = os.path.abspath(args.skill_dir)
    source_backup_dir = Path(args.backup_dir)
    if not source_backup_dir.is_dir():
        print(json.dumps({"status": "failed", "errors": [f"backup dir does not exist: {args.backup_dir}"]}))
        return 1

    plan = load_json(source_backup_dir / PLAN_FILE, None)
    if not isinstance(plan, dict):
        print(json.dumps({"status": "failed", "errors": [f"missing or invalid {PLAN_FILE}"]}))
        return 1

    try:
        scoped_plan, scoped_project = scope_plan(plan, args.project)
    except ValueError as exc:
        print(json.dumps({"status": "failed", "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 1

    if args.output_dir:
        sandbox_dir = Path(args.output_dir).expanduser().resolve()
        sandbox_dir.mkdir(parents=True, exist_ok=True)
    else:
        sandbox_dir = Path(tempfile.mkdtemp(prefix=f"trailkeep-review-test-{slug(args.project)}-"))

    write_json(sandbox_dir / PLAN_FILE, scoped_plan)
    copy_if_exists(source_backup_dir / BACKUP_LOG_FILE, sandbox_dir / BACKUP_LOG_FILE)

    projects_doc = load_json(source_backup_dir / PROJECTS_FILE, {})
    write_json(sandbox_dir / PROJECTS_FILE, filter_projects_doc(projects_doc, args.project))

    preprocessed_doc = load_json(source_backup_dir / PREPROCESSED_INPUTS_FILE, {})
    write_json(sandbox_dir / PREPROCESSED_INPUTS_FILE, filter_preprocessed(preprocessed_doc, scoped_project))

    selected_ids, linked_markdowns = selected_conversation_paths(
        scoped_project,
        source_backup_dir,
        sandbox_dir,
        args.copy_files,
    )

    summaries_doc = load_json(source_backup_dir / CONVERSATION_SUMMARIES_FILE, {})
    write_json(
        sandbox_dir / CONVERSATION_SUMMARIES_FILE,
        filter_conversation_summaries(summaries_doc, args.project, selected_ids),
    )

    reviews_doc = load_json(source_backup_dir / PROJECT_REVIEWS_FILE, {})
    write_json(sandbox_dir / PROJECT_REVIEWS_FILE, filter_project_reviews(reviews_doc, args.project))

    profile_doc = load_json(source_backup_dir / AGENT_PROFILE_FILE, None)
    write_json(sandbox_dir / AGENT_PROFILE_FILE, profile_doc if isinstance(profile_doc, dict) else empty_agent_profile())
    write_json(sandbox_dir / REVIEW_UPDATE_LOG_FILE, {"version": 1, "runs": []})

    eval_output = ""
    gate_output = ""
    if not args.skip_gate:
        try:
            eval_output, gate_output = run_eval_and_gate(args, sandbox_dir)
        except RuntimeError as exc:
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "sandbox_dir": str(sandbox_dir),
                        "errors": [str(exc).strip()],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

    prompt_path = sandbox_dir / "project-review-test-prompt.txt"
    instructions_path = sandbox_dir / "testing-instructions.md"
    prompt_path.write_text(render_test_prompt(args, sandbox_dir, scoped_project, linked_markdowns), encoding="utf-8")
    instructions_path.write_text(render_instructions(args, sandbox_dir, prompt_path), encoding="utf-8")

    payload = {
        "status": "ok",
        "project": args.project,
        "sandbox_dir": str(sandbox_dir),
        "prompt_file": str(prompt_path),
        "instructions_file": str(instructions_path),
        "review_run_plan": PLAN_FILE,
        "review_eval_report": PLAN_EVAL_FILE,
        "review_effective_plan": EFFECTIVE_PLAN_FILE if (sandbox_dir / EFFECTIVE_PLAN_FILE).exists() else "",
        "linked_markdowns": len(linked_markdowns),
        "selected_inputs": len(scoped_project.get("selected_inputs") or []),
        "estimated_input_tokens": scoped_project.get("estimate", {}).get("input_tokens", 0),
        "output_language": args.output_language,
        "eval": eval_output,
        "gate": json.loads(gate_output) if gate_output else {},
        "message": "Paste project-review-test-prompt.txt into the coding agent to test this project without touching the real backup folder.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
