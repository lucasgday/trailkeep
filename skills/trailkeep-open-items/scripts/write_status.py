#!/usr/bin/env python3
"""Render a project's open items into its repo STATUS.md, merged with any existing one.

Deterministic, $0, on-device. Reads <backup_dir>/_open_items.json and the repo's
current STATUS.md (if any). Existing bullets are kept (they are usually newer
than the conversations); generated items are added unless they duplicate one.
Prints the result; writes only with --write. Never commits.

Usage:
  write_status.py BACKUP_DIR --project NAME [--project NAME ...] [--agent NAME] [--write]
"""

import argparse
import datetime
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "converters"))

from atomic_io import atomic_write_text  # noqa: E402
from plan_reviews import load_json  # noqa: E402

SECTIONS = ["Probar", "Destrabar", "Pendiente sin backlog", "Último cambio", "Próxima sesión"]
EMPTY = "Nada."
WORD = re.compile(r"[a-záéíóúñü0-9]{4,}")


BOLD_LABEL = re.compile(r"^\*\*(" + "|".join(map(re.escape, SECTIONS)) + r")\*\*[\s:]*(.*)$")
NOTHING = re.compile(r"^(?:-\s*)?Nada\b", re.I)


def parse_status(text):
    """Split STATUS.md into sections; accepts `## Name` or `**Name**` labels.

    Lines outside any known section (besides the title and date line) are kept
    under "Notas" so merging never drops what someone wrote by hand.
    """
    sections, order, current = {}, [], None

    def start(name):
        if name not in sections:
            sections[name] = []
            order.append(name)
        return name

    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        bold = BOLD_LABEL.match(line)
        if heading:
            current = start(heading.group(1))
        elif bold:
            current = start(bold.group(1))
            if bold.group(2).strip():
                sections[current].append(bold.group(2).strip())
        elif current is None:
            if line.strip() and not re.match(r"^#\s|^_Actualizado", line):
                sections.setdefault("Notas", []).append(line)
                if "Notas" not in order:
                    order.append("Notas")
        elif "`_open_items.json` de trailkeep" not in line:
            sections[current].append(line)
    for name in sections:
        lines = sections[name]
        while lines and not lines[-1].strip():
            lines.pop()
        while lines and not lines[0].strip():
            lines.pop(0)
        if [line.strip() for line in lines] == [EMPTY]:
            sections[name] = []
    return sections, order


def words(text):
    return set(WORD.findall(text.lower()))


def is_duplicate(text, existing_lines):
    new = words(text)
    if not new:
        return False
    for line in existing_lines:
        old = words(line)
        if old and len(new & old) / min(len(new), len(old)) >= 0.6:
            return True
    return False


def ref(item):
    evidence = item.get("evidence") or []
    if not evidence:
        return ""
    first = evidence[0]
    return f" _(conv {first.get('date', '')} · {str(first.get('id', ''))[:8]})_"


def bullet_test(item):
    how = f" Cómo: {item['how']}" if item.get("how") else ""
    return f"- {item['text']}{how}{ref(item)}"


def bullet_unblock(item):
    options = " / ".join(item.get("options") or [])
    return f"- {item['text']} **Recomiendo:** {item.get('recommendation', '')} (opciones: {options}){ref(item)}"


def bullet_pending(item):
    return f"- {item['text']}{ref(item)}"


def merge_bullets(existing, generated):
    out = list(existing)
    for line in generated:
        if not is_duplicate(line, out):
            out.append(line)
    if any(not NOTHING.match(line.strip()) for line in out if line.strip()):
        out = [line for line in out if not NOTHING.match(line.strip())]
    return out


def last_commit(repo):
    try:
        return subprocess.run(
            ["git", "-C", repo, "log", "-1", "--date=short", "--format=%ad · %s (%h)"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def render(project, entry, existing_text, agent):
    sections, order = parse_status(existing_text)
    repo = entry.get("repo_path") or ""
    probar = merge_bullets(sections.get("Probar", []), [bullet_test(i) for i in entry.get("test", [])])
    destrabar = merge_bullets(
        sections.get("Destrabar", []), [bullet_unblock(i) for i in entry.get("unblock", [])])
    pending = merge_bullets(
        sections.get("Pendiente sin backlog", []),
        [bullet_pending(i) for i in entry.get("pending", []) if not i.get("backlog_ref")],
    )
    commit = last_commit(repo) if repo else ""
    last = sections.get("Último cambio") or ([f"- {commit}"] if commit else [])
    next_session = sections.get("Próxima sesión") or [entry.get("next_session", "")]

    today = datetime.date.today().isoformat()
    out = ["# Estado", "", f"_Actualizado {today} · {agent}_", ""]
    for name, lines in zip(SECTIONS, [probar, destrabar, pending, last, next_session]):
        lines = [line for line in lines if line.strip()]
        out += [f"## {name}", ""] + (lines or [EMPTY]) + [""]
    for name in order:
        if name not in SECTIONS and sections[name]:
            out += [f"## {name}", ""] + sections[name] + [""]
    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup_dir")
    ap.add_argument("--project", action="append", required=True)
    ap.add_argument("--agent", default="trailkeep open-items")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    data = load_json(os.path.join(os.path.abspath(args.backup_dir), "_open_items.json"), {})
    failed = False
    for project in args.project:
        entry = (data.get("projects") or {}).get(project)
        if not entry:
            print(f"!! {project}: not in _open_items.json", file=sys.stderr)
            failed = True
            continue
        repo = entry.get("repo_path") or ""
        if not repo or not os.path.isdir(repo):
            print(f"!! {project}: repo path missing ({repo or 'unknown'})", file=sys.stderr)
            failed = True
            continue
        path = os.path.join(repo, "STATUS.md")
        existing = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        text = render(project, entry, existing, args.agent)
        print(f"===== {path}{' (merged)' if existing else ''}\n{text}")
        if args.write:
            atomic_write_text(path, text)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
