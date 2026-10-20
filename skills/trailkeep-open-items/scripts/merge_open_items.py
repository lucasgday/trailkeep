#!/usr/bin/env python3
"""Validate one project's open-items result and merge it into _open_items.json.

Deterministic, $0, on-device. Checks the schema, that every evidence ref points
to a conversation present in that project's digest, and that no secret pattern
leaked. On success the project entry is atomically replaced inside
<backup_dir>/_open_items.json; other projects are kept (cumulative). Exits 1
with the list of problems otherwise.

Usage:
  merge_open_items.py BACKUP_DIR PROJECT RESULT_JSON --model NAME
"""

import argparse
import datetime
import fcntl
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "converters"))

from atomic_io import atomic_write_json  # noqa: E402
from plan_reviews import load_json, possible_secret  # noqa: E402

VERSION = 1
OUTPUT_FILE = "_open_items.json"
LISTS = ("pending", "unblock", "test", "decisions")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_item(kind, idx, item, known_ids, problems):
    where = f"{kind}[{idx}]"
    if not isinstance(item, dict):
        problems.append(f"{where}: not an object")
        return
    if not str(item.get("text") or "").strip():
        problems.append(f"{where}: empty text")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        problems.append(f"{where}: needs at least one evidence ref")
    else:
        for ref in evidence:
            if not isinstance(ref, dict) or ref.get("id") not in known_ids:
                problems.append(f"{where}: evidence id not in digest: {ref!r}")
            elif not DATE.match(str(ref.get("date") or "")):
                problems.append(f"{where}: evidence date must be YYYY-MM-DD: {ref!r}")
    if kind == "unblock":
        options = item.get("options")
        if not isinstance(options, list) or len(options) < 2:
            problems.append(f"{where}: unblock items need at least two options")
        if not str(item.get("recommendation") or "").strip():
            problems.append(f"{where}: unblock items need a recommendation")


def validate(result, known_ids):
    problems = []
    if not isinstance(result, dict):
        return ["result is not an object"]
    for kind in LISTS:
        items = result.get(kind)
        if not isinstance(items, list):
            problems.append(f"{kind}: must be a list")
            continue
        for idx, item in enumerate(items):
            check_item(kind, idx, item, known_ids, problems)
    if not isinstance(result.get("resolved", []), list):
        problems.append("resolved: must be a list")
    next_session = result.get("next_session")
    if not isinstance(next_session, str) or not next_session.strip():
        problems.append("next_session: required string")
    elif len(next_session) > 800:
        problems.append("next_session: keep it to 2-4 lines")
    if possible_secret(json.dumps(result, ensure_ascii=False)):
        problems.append("possible secret in result; redact and retry")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backup_dir")
    ap.add_argument("project")
    ap.add_argument("result_json")
    ap.add_argument("--model", required=True)
    args = ap.parse_args()

    backup_dir = os.path.abspath(args.backup_dir)
    manifest = load_json(os.path.join(backup_dir, "_open_items_inputs", "_manifest.json"), {})
    entry = manifest.get(args.project)
    if not entry:
        sys.exit(f"project not in digest manifest: {args.project}")
    try:
        with open(args.result_json, encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError) as exc:
        sys.exit(f"cannot read result: {exc}")

    problems = validate(result, set(entry.get("conversation_ids") or []))
    if problems:
        print("\n".join(problems))
        sys.exit(1)

    out_path = os.path.join(backup_dir, OUTPUT_FILE)
    # Batches of different projects may finish together; serialize the merge.
    lock = open(out_path + ".lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    data = load_json(out_path, {"version": VERSION, "projects": {}})
    data["version"] = VERSION
    data.setdefault("projects", {})[args.project] = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": args.model,
        "repo_path": entry.get("repo_path") or "",
        "coverage": {
            "conversations": entry.get("conversations", 0),
            "first_date": entry.get("first_date", ""),
            "last_date": entry.get("last_date", ""),
        },
        **{kind: result[kind] for kind in LISTS},
        "resolved": result.get("resolved", []),
        "next_session": result["next_session"].strip(),
    }
    atomic_write_json(out_path, data)
    counts = ", ".join(f"{k}={len(result[k])}" for k in LISTS)
    print(f"ok {args.project}: {counts}, resolved={len(result.get('resolved', []))}")


if __name__ == "__main__":
    main()
