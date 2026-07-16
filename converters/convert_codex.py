#!/usr/bin/env python3
"""Convert Codex sessions (rollout-*.jsonl) into readable Markdown.
Cross-references session_index.jsonl for the title (thread_name) and uses
session_meta for date/project.
Usage: convert_codex.py <sessions_dir> <session_index.jsonl> <output_dir>
"""
import json, os, re, sys, glob
from collections import Counter

from atomic_io import atomic_write_json, atomic_write_text

def load_index(index_path):
    idx = {}
    if not os.path.exists(index_path):
        return idx
    for line in open(index_path):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if "id" in d:
            idx[d["id"]] = {
                "title": d.get("thread_name"),
                "updated_at": d.get("updated_at"),
            }
    return idx

def text_from_content(content):
    """content is a list of {type, text} blocks. Returns plain text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for c in content:
        if isinstance(c, dict):
            # input_text / output_text / text
            t = c.get("text")
            if t:
                parts.append(t)
        elif isinstance(c, str):
            parts.append(c)
    return "\n".join(p for p in parts if p)

def fmt_function_call(payload):
    name = payload.get("name", "tool")
    args = payload.get("arguments")
    if args is None:
        args = payload.get("input", "")
    try:
        a = json.loads(args) if isinstance(args, str) else args
        if name == "spawn_agent" and isinstance(a, dict) and a.get("task_name"):
            return f"[tool: spawn_agent → {a['task_name']}]"
        if isinstance(a, dict) and ("command" in a or "cmd" in a):
            cmd = a.get("command", a.get("cmd"))
            if isinstance(cmd, list):
                cmd = " ".join(cmd)
            return f"[tool: {name}]\n```bash\n{cmd}\n```"
        blob = json.dumps(a, ensure_ascii=False)
    except Exception:
        blob = str(args)
        if len(blob) > 500:
            blob = blob[:500] + " …"
        return f"[tool: {name}]\n```\n{blob}\n```" if blob.strip() else f"[tool: {name}]"
    if len(blob) > 300:
        blob = blob[:300] + " …"
    return f"[tool: {name} {blob}]"

def fmt_function_output(payload):
    out = payload.get("output", "")
    if isinstance(out, (dict, list)):
        out = json.dumps(out, ensure_ascii=False)
    out = str(out).strip()
    if len(out) > 500:
        out = out[:500] + " …(truncated)"
    return f"[result]\n```\n{out}\n```" if out else ""

def msg_to_md(role, content):
    txt = text_from_content(content)
    if not txt.strip():
        return None
    label = "You" if role == "user" else "Codex"
    return f"### {label}\n\n{txt}\n"

def instruction_context_title(s):
    if not s:
        return False
    first = next((line.strip() for line in str(s).strip().splitlines() if line.strip()), "")
    return bool(re.match(r"^#?\s*AGENTS\.md instructions for\b", first, re.I))

def clean_title(s):
    if not s:
        return None
    if instruction_context_title(s):
        return None
    first = next((line.strip() for line in str(s).strip().splitlines() if line.strip()), "")
    first = re.sub(r"^#+\s*", "", first).strip()
    if not first or instruction_context_title(first):
        return None
    if len(first) > 70:
        cut = first[:70].rsplit(" ", 1)[0]
        first = (cut or first[:70]) + "…"
    return first

def subagent_meta(source):
    if not isinstance(source, dict):
        return None
    subagent = source.get("subagent")
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    if not isinstance(spawn, dict) or not spawn.get("parent_thread_id"):
        return None
    return {
        "parent_id": str(spawn.get("parent_thread_id") or ""),
        "agent_path": str(spawn.get("agent_path") or ""),
        "agent_nickname": str(spawn.get("agent_nickname") or ""),
        "agent_depth": spawn.get("depth"),
    }

def subagent_title(meta):
    path = str((meta or {}).get("agent_path") or "").rstrip("/")
    raw = path.rsplit("/", 1)[-1] if path else ""
    title = re.sub(r"[_-]+", " ", raw).strip()
    if not title:
        title = str((meta or {}).get("agent_nickname") or "").strip()
    return title[:1].upper() + title[1:] if title else None

def json_lines(path):
    with open(path, errors="ignore") as source:
        for line_no, line in enumerate(source, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_no, json.loads(line)
            except Exception:
                continue

def message_fingerprint(payload):
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return ""
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return ""

def parse_session(path, index, archived=False):
    sid = None
    sess_ts = None
    cwd = None
    blocks = []
    child = None
    boundary_line = None
    completed_at = ""
    status = ""
    replayed_parent = False
    last_task_started_line = None
    last_line = 0
    message_fingerprints = []

    # Codex fork rollouts begin with the child's session_meta, then may replay a
    # large slice of the parent's history (including the parent's session_meta).
    # The inter-agent marker is the stable boundary before the child's own turn.
    # Identity therefore comes from the FIRST session_meta only.
    for line_no, d in json_lines(path):
        last_line = line_no
        if d.get("type") == "session_meta" and sid is None:
            payload = d.get("payload", {}) or {}
            sid = payload.get("id")
            sess_ts = payload.get("timestamp") or d.get("timestamp")
            cwd = payload.get("cwd")
            child = subagent_meta(payload.get("source"))
        elif child and d.get("type") == "session_meta":
            replay_id = str((d.get("payload", {}) or {}).get("id") or "")
            if replay_id and replay_id != str(sid or ""):
                replayed_parent = True
        if child and d.get("type") == "response_item":
            fingerprint = message_fingerprint(d.get("payload", {}) or {})
            if fingerprint:
                message_fingerprints.append((line_no, fingerprint))
        if child and d.get("type") == "event_msg" \
                and (d.get("payload", {}) or {}).get("type") == "task_started":
            last_task_started_line = line_no
        if child and d.get("type") == "inter_agent_communication_metadata":
            boundary_line = line_no
            break

    # Some Codex versions omit the explicit inter-agent marker after replaying
    # a different parent session. The final task_started is the conservative
    # boundary for the child's own turn. If even that is absent, skip the whole
    # replay rather than mislabeling parent history as child-authored content.
    if child and boundary_line is None and replayed_parent:
        boundary_line = last_task_started_line or last_line
    inherited_messages = Counter(
        fingerprint for line_no, fingerprint in message_fingerprints
        if boundary_line is not None and line_no <= boundary_line
    )

    for line_no, d in json_lines(path):
        typ = d.get("type")
        payload = d.get("payload", {}) or {}

        if typ == "session_meta":
            continue

        # Child rollouts may replay parent context before either an explicit
        # marker or the conservative markerless fallback boundary above.
        if child and boundary_line is not None and line_no <= boundary_line:
            continue

        elif typ == "response_item":
            ptype = payload.get("type")
            if ptype == "message":
                role = payload.get("role")
                if role in ("user", "assistant"):
                    md = msg_to_md(role, payload.get("content", []))
                    if md:
                        blocks.append(md)
                # developer / system → ignored (internal instructions)
            elif ptype in ("function_call", "custom_tool_call"):
                blocks.append("### Codex\n\n" + fmt_function_call(payload) + "\n")
            elif ptype in ("function_call_output", "custom_tool_call_output"):
                out = fmt_function_output(payload)
                if out:
                    blocks.append("### Codex\n\n" + out + "\n")
            # reasoning → ignored (internal reasoning)

        elif typ == "compacted":
            # recover history that the compaction replaced
            inherited_remaining = Counter(inherited_messages)
            for m in payload.get("replacement_history", []):
                if isinstance(m, dict) and m.get("type") == "message":
                    fingerprint = message_fingerprint(m)
                    if child and boundary_line is not None and inherited_remaining[fingerprint]:
                        inherited_remaining[fingerprint] -= 1
                        continue
                    role = m.get("role")
                    if role in ("user", "assistant"):
                        md = msg_to_md(role, m.get("content", []))
                        if md:
                            blocks.append(md)

        elif typ == "event_msg":
            event_type = payload.get("type")
            if event_type == "task_complete":
                status = "completed"
                completed_at = d.get("timestamp") or ""

    if child and not status:
        status = "in_progress"

    # title: from the index if present, else first user message, else date
    meta = index.get(sid, {}) if sid else {}
    title = subagent_title(child) if child else clean_title(meta.get("title"))
    updated = meta.get("updated_at") or sess_ts
    if not title:
        # look for the first "### You"
        for b in blocks:
            if b.startswith("### You"):
                body = b.split("\n\n", 1)[1] if "\n\n" in b else ""
                title = clean_title(body)
                if title:
                    break
    if not title:
        title = "session-" + (sid or os.path.basename(path))[:20]

    project = ""
    if cwd:
        project = os.path.basename(cwd.rstrip("/"))

    return {
        "id": sid,
        "title": title,
        "date": (updated or "")[:10],
        "datetime": updated or "",
        "project": project,
        "blocks": blocks,
        "archived": archived,
        "parent_id": (child or {}).get("parent_id", ""),
        "agent_path": (child or {}).get("agent_path", ""),
        "agent_nickname": (child or {}).get("agent_nickname", ""),
        "agent_depth": (child or {}).get("agent_depth"),
        "agent_status": status,
        "completed_at": completed_at,
        "deferred": bool(child and not blocks and status != "completed"),
        "unreadable_completed": bool(child and not blocks and status == "completed"),
    }

def safe_filename(s):
    s = re.sub(r"[^\w\s-]", "", s).strip().replace(" ", "_")
    return s[:80] or "session"

def meta_value(body, key):
    m = re.search(rf"(?:^|\|)\s*{re.escape(key)}\s*:\s*([^|]*?)\s*(?=\||$)", body, re.I)
    return m.group(1).strip() if m and m.group(1).strip() else ""

def existing_markdowns_by_id(out_dir):
    existing = {}
    if not os.path.isdir(out_dir):
        return existing
    for path in glob.glob(os.path.join(out_dir, "**", "*.md"), recursive=True):
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                head = f.read(4096)
        except Exception:
            continue
        comment = re.search(r"<!--(.*?)-->", head, re.S)
        if not comment:
            continue
        body = comment.group(1)
        sid = meta_value(body, "id")
        if not sid:
            continue
        date = meta_value(body, "date") or meta_value(body, "fecha")
        current = existing.get(sid)
        if current is None or (date, path) > (current["date"], current["path"]):
            existing[sid] = {"date": date, "path": path}
    return existing

def main():
    sessions_dir, index_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    archived = len(sys.argv) > 4 and sys.argv[4].lower() in ("1","true","archived","yes")
    index = load_index(index_path)
    files = glob.glob(os.path.join(sessions_dir, "**", "*.jsonl"), recursive=True)

    counts = {"ok": 0, "empty": 0, "subagents": 0, "deferred": 0, "unreadable": 0}
    existing_by_id = existing_markdowns_by_id(out_dir)
    for f in files:
        s = parse_session(f, index, archived=archived)
        if not s["blocks"]:
            if s["deferred"]:
                counts["deferred"] += 1
            elif s["unreadable_completed"]:
                counts["unreadable"] += 1
            else:
                counts["empty"] += 1
            continue
        proj = s["project"] or "no-project"
        pdir = os.path.join(out_dir, proj)
        os.makedirs(pdir, exist_ok=True)

        base = safe_filename(s["title"])
        # date prefix (chronological order) + short UUID suffix (guaranteed uniqueness)
        prefix = (s["date"] or "0000-00-00")
        uid = (s["id"] or "") or os.path.splitext(os.path.basename(f))[0]
        fname = f"{prefix}__{base}__{uid}.md"
        out_path = existing_by_id.get(uid, {}).get("path") if s["id"] else ""
        if not out_path:
            out_path = os.path.join(pdir, fname)
            if s["id"]:
                existing_by_id[s["id"]] = {"date": s["datetime"] or s["date"] or "", "path": out_path}

        metadata = [
            f"date: {s['datetime']}", f"id: {s['id']}", f"project: {proj}",
            "source: codex", f"archived: {str(s['archived']).lower()}",
            "format_version: 2",
        ]
        if s["parent_id"]:
            metadata.extend([
                f"parent_id: {s['parent_id']}",
                f"agent_path: {s['agent_path']}",
                f"agent_nickname: {s['agent_nickname']}",
                f"agent_depth: {s['agent_depth'] if s['agent_depth'] is not None else ''}",
                f"agent_status: {s['agent_status']}",
                f"completed_at: {s['completed_at']}",
            ])
        body = f"# {s['title']}\n\n<!-- {' | '.join(metadata)} -->\n\n" + "\n".join(s["blocks"])
        atomic_write_text(out_path, body)
        counts["ok"] += 1
        if s["parent_id"]:
            counts["subagents"] += 1

    print(f"Converted: {counts['ok']}")
    print(f"Subagents: {counts['subagents']}")
    print(f"Deferred subagents: {counts['deferred']}")
    print(f"Unreadable completed subagents: {counts['unreadable']}")
    print(f"Empty (no readable messages): {counts['empty']}")

    # backup stamp: timestamp of this run
    try:
        import datetime
        info_path = os.path.join(out_dir, "_backup-info.json")
        info = {}
        if os.path.exists(info_path):
            try: info = json.load(open(info_path))
            except Exception: info = {}
        key = "codex-archived" if archived else "codex"
        info[key] = {
            "generated": datetime.datetime.now().astimezone().isoformat(),
            "conversations": counts["ok"],
            "subagents": counts["subagents"],
            "deferred_subagents": counts["deferred"],
            "unreadable_completed_subagents": counts["unreadable"],
        }
        os.makedirs(out_dir, exist_ok=True)
        atomic_write_json(info_path, info)
    except Exception:
        pass

if __name__ == "__main__":
    main()
