#!/usr/bin/env python3
"""Small atomic-write helpers for trailkeep-generated files."""

import json
import os
import tempfile


def atomic_write_text(path, text, encoding="utf-8"):
    """Replace path only after the complete text is durable on disk."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=directory,
        prefix=f".{os.path.basename(path)}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(path, value):
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
