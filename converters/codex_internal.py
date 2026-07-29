"""Shared recognition helpers for Codex rollouts.

Codex Desktop stores its permission reviewer ("guardian") beside user-owned
rollouts. Those transcripts are implementation machinery, not conversations:
their user turns contain an approval-assessment prompt and their assistant turns
contain small JSON decisions such as {"outcome":"allow"}.

Raw readers should prefer the stable session_meta source marker. Markdown
readers also need the conservative content fallback because trailkeep backups
are cumulative and older converted guardian files must remain on disk.
"""
import datetime
import json
import re


APPROVAL_REVIEW_PROMPT = re.compile(
    r"^The following is the Codex agent history "
    r"(?:whose request action you are assessing|added since your last approval assessment)\b",
    re.I,
)
MARKDOWN_TURN = re.compile(
    r"(?ims)^###\s+(You|Tú|Tu|User|Codex)\s*$\n+(.*?)(?=^###\s+|\Z)"
)


def is_guardian_source(source):
    """Return True only for Codex's explicit internal guardian marker."""
    if not isinstance(source, dict):
        return False
    subagent = source.get("subagent")
    return isinstance(subagent, dict) and subagent.get("other") == "guardian"


def latest_timestamp(*values):
    """Return the chronologically latest parseable ISO timestamp."""
    candidates = [str(value).strip() for value in values if str(value or "").strip()]
    if not candidates:
        return None

    def key(value):
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return 1, parsed.timestamp(), value
        except (TypeError, ValueError, OverflowError):
            return 0, 0, value

    return max(candidates, key=key)


def _instruction_context(text):
    first = next(
        (line.strip() for line in str(text or "").strip().splitlines() if line.strip()),
        "",
    )
    return bool(re.match(r"^#?\s*AGENTS\.md instructions for\b", first, re.I))


def _approval_outcome(text):
    try:
        value = json.loads(str(text or "").strip())
    except Exception:
        return False
    return isinstance(value, dict) and isinstance(value.get("outcome"), str)


def is_legacy_guardian_markdown(text, source, parent_id=""):
    """Recognize already-converted guardian Markdown without hiding real chats.

    A match requires a root Codex session where every non-instruction user turn
    is an approval-review prompt and at least one Codex turn is a JSON outcome.
    This intentionally does not match a normal conversation that merely quotes
    or discusses one of the guardian prompts.
    """
    if str(source or "").strip().lower() != "codex" or str(parent_id or "").strip():
        return False

    user_turns = []
    assistant_turns = []
    for speaker, body in MARKDOWN_TURN.findall(text or ""):
        if speaker.lower() in ("you", "tú", "tu", "user"):
            if not _instruction_context(body):
                user_turns.append(body.strip())
        else:
            assistant_turns.append(body.strip())

    return (
        bool(user_turns)
        and all(APPROVAL_REVIEW_PROMPT.match(turn) for turn in user_turns)
        and any(_approval_outcome(turn) for turn in assistant_turns)
    )
