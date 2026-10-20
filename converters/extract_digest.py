#!/usr/bin/env python3
"""Build compact per-project conversation digests for open-items extraction.

Deterministic, $0, on-device. Reads the Markdown backups and writes a
Markdown digest per project under <backup_dir>/_open_items_inputs/<project>/,
split into parts small enough for one agent read and grouped into batches that
fit one agent context. A digest
keeps every exchange of every conversation (the user's message plus the last
assistant text reply before the next user message) and drops tool calls and
tool results, so long conversations without a closing summary still show what
was asked, what was answered and where the thread stopped. When a conversation
exceeds its budget, the oldest exchanges are shortened first and the newest
stay intact. Secrets are redacted before writing. No LLM, no network.

Usage:
  extract_digest.py BACKUP_DIR [--project NAME ...] [--max-chars N]
"""

import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from atomic_io import atomic_write_json, atomic_write_text  # noqa: E402
from plan_reviews import (  # noqa: E402
    load_json,
    markdown_sessions,
    redact_secrets,
    sanitize_instruction_context,
)

OUTPUT_DIR = "_open_items_inputs"
USER_HEADERS = {"you", "tú", "tu", "user"}
TURN = re.compile(r"(?m)^###\s+(.+?)\s*$")
NOISE_BLOCKS = [
    re.compile(r"(?is)<system-reminder>.*?</system-reminder>"),
    re.compile(r"(?is)<local-command-stdout>.*?</local-command-stdout>"),
    re.compile(r"(?is)<command-(?:name|message|args)>.*?</command-(?:name|message|args)>"),
    re.compile(r"(?is)\[INSTRUCTION_CONTEXT_\d+:[^\]]*\]"),
]
COMMIT_HINT = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?(commit|push)\b")
# A title repeated this many times inside one project is treated as a
# scheduled/automated run (e.g. a daily trading update) and skipped.
AUTOMATION_TITLE_REPEATS = 4
DEFAULT_MAX_CHARS = 40000
PART_CHARS = 80000
BATCH_CHARS = 480000
USER_CAP, AGENT_CAP = 1500, 1200
USER_SHORT, AGENT_SHORT = 300, 200


def clean(text):
    for pattern in NOISE_BLOCKS:
        text = pattern.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clip(text, limit):
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"


def exchanges(text):
    """Split a conversation into [{user, agent, tools, committed}] exchanges."""
    text, _ = sanitize_instruction_context(text)
    parts = TURN.split(text)
    out = []
    current = None
    for i in range(1, len(parts) - 1, 2):
        header, body = parts[i].strip(), parts[i + 1].strip()
        is_user_header = header.lower() in USER_HEADERS
        if is_user_header and not body.startswith("[result]"):
            body = clean(body)
            if not body:
                continue
            current = {"user": body, "agent": "", "tools": 0, "committed": False}
            out.append(current)
            continue
        if current is None:
            continue
        if body.startswith("[tool:"):
            current["tools"] += 1
            if COMMIT_HINT.search(body):
                current["committed"] = True
        elif not is_user_header:
            reply = clean(body)
            if reply:
                current["agent"] = reply
    return out


def render_exchange(ex, user_cap, agent_cap):
    lines = [f"- **Lucas:** {clip(ex['user'], user_cap)}"]
    notes = []
    if ex["tools"]:
        notes.append(f"{ex['tools']} tool calls")
    if ex["committed"]:
        notes.append("ran git commit/push")
    agent = clip(ex["agent"], agent_cap) if ex["agent"] else "(no text reply)"
    suffix = f" _({', '.join(notes)})_" if notes else ""
    lines.append(f"  **Agent:** {agent}{suffix}")
    return "\n".join(lines).replace("\n", "\n  ")


def render_conversation(session, max_chars):
    exs = exchanges(session["text"])
    head = (
        f"## {session['date'][:10]} · {session['title']}\n"
        f"id: {session['id']} · source: {session['source']} · exchanges: {len(exs)}\n"
    )
    if not exs:
        return head + "\n(no user messages)\n"
    full = [render_exchange(e, USER_CAP, AGENT_CAP) for e in exs]
    rendered = list(full)
    # Shorten oldest exchanges first; the end of the thread matters most.
    i = 0
    while sum(map(len, rendered)) > max_chars and i < len(rendered) - 3:
        rendered[i] = render_exchange(exs[i], USER_SHORT, AGENT_SHORT)
        i += 1
    omitted = 0
    while sum(map(len, rendered)) > max_chars and len(rendered) > 6:
        del rendered[3]
        omitted += 1
    if omitted:
        rendered.insert(3, f"- _[{omitted} middle exchanges omitted for length]_")
    return head + "\n" + "\n".join(rendered) + "\n"


def build(backup_dir, projects_filter, max_chars):
    sessions = markdown_sessions(backup_dir)
    meta = load_json(os.path.join(backup_dir, "_projects.json"), {}).get("projects", {})
    by_project = collections.defaultdict(list)
    for s in sessions:
        by_project[s["project"]].append(s)

    out_dir = os.path.join(backup_dir, OUTPUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "_manifest.json")
    manifest = load_json(manifest_path, {}) if projects_filter else {}
    built = {}
    for project, items in sorted(by_project.items()):
        if projects_filter and project not in projects_filter:
            continue
        titles = collections.Counter(s["title"] for s in items)
        kept, skipped = [], collections.Counter()
        for s in items:
            if re.search(r"parent_id:\s*\S", s["text"][:600]):
                skipped["subagent"] += 1
            elif titles[s["title"]] >= AUTOMATION_TITLE_REPEATS and not s["title"].startswith("<"):
                skipped["automated"] += 1
            else:
                kept.append(s)
        kept.sort(key=lambda s: (s["date"], s["path"]))
        info = meta.get(project) or {}
        header = [
            f"# Conversation digest: {project}",
            "",
            f"repo_path: {info.get('path') or '(unknown)'}",
            f"conversations: {len(kept)} (oldest first)",
            f"skipped: {dict(skipped) or 'none'}",
            "",
        ]
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", project).strip("_") or "_unnamed"
        project_dir = os.path.join(out_dir, safe)
        os.makedirs(project_dir, exist_ok=True)
        for stale in os.listdir(project_dir):
            if re.match(r"part-\d+\.md$", stale):
                os.remove(os.path.join(project_dir, stale))
        parts, current = [], "\n".join(header) + "\n"
        for s in kept:
            block, _ = redact_secrets(render_conversation(s, max_chars))
            if len(current) + len(block) > PART_CHARS and current.strip():
                parts.append(current)
                current = f"# Conversation digest: {project} (continued)\n\n"
            current += block + "\n"
        parts.append(current)
        names, batches, batch, batch_chars = [], [], [], 0
        for n, text in enumerate(parts, 1):
            name = f"part-{n:03d}.md"
            atomic_write_text(os.path.join(project_dir, name), text)
            names.append(name)
            if batch and batch_chars + len(text) > BATCH_CHARS:
                batches.append(batch)
                batch, batch_chars = [], 0
            batch.append(name)
            batch_chars += len(text)
        batches.append(batch)
        built[project] = manifest[project] = {
            "dir": os.path.relpath(project_dir, backup_dir),
            "repo_path": info.get("path") or "",
            "conversations": len(kept),
            "conversation_ids": [s["id"] for s in kept],
            "skipped": dict(skipped),
            "first_date": kept[0]["date"][:10] if kept else "",
            "last_date": kept[-1]["date"][:10] if kept else "",
            "estimated_tokens": sum(map(len, parts)) // 4,
            "parts": names,
            "batches": batches,
        }
    atomic_write_json(manifest_path, manifest)
    return built


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup_dir")
    ap.add_argument("--project", action="append", default=[])
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                    help="per-conversation character budget (default %(default)s)")
    args = ap.parse_args()
    manifest = build(os.path.abspath(args.backup_dir), set(args.project), args.max_chars)
    total = sum(m["estimated_tokens"] for m in manifest.values())
    for name, m in sorted(manifest.items(), key=lambda kv: -kv[1]["estimated_tokens"]):
        print(f"{name:32} {m['conversations']:5} convs {m['estimated_tokens']:9} tok  skipped={m['skipped']}")
    print(f"total ~{total} tokens across {len(manifest)} projects")


if __name__ == "__main__":
    main()
