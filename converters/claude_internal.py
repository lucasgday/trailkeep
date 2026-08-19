"""Shared recognition helpers for Claude Code internal local-command sessions.

Claude Code stores slash-command UI traffic beside real conversations. A
session such as ``/config`` can contain only generated wrapper messages like
``<local-command-caveat>`` and ``<local-command-stdout>`` with no assistant
work. Those records are local UI machinery, not user conversations.

Raw readers should classify the message content directly. Markdown readers
also need the conservative fallback because trailkeep backups are cumulative
and older converted command-only files must remain on disk.
"""
import re


LOCAL_COMMAND_START = re.compile(
    r"^<(?:local-command-(?:caveat|stdout|stderr|result)|command-(?:name|message|args))\b",
    re.I,
)
MARKDOWN_TURN = re.compile(
    r"(?ims)^###\s+(You|Tú|Tu|User|Claude)\s*$\n+(.*?)(?=^###\s+|\Z)"
)
CONFIG_TITLE = re.compile(r"(?im)^#\s+/?config\s*$")
CONFIG_TOOL_BODY = re.compile(r"(?is)^\[tool:\s*AskUserQuestion\b.*\]\s*$")


def is_local_command_text(text):
    """Return True only for a known generated local-command wrapper."""
    return bool(LOCAL_COMMAND_START.match(str(text or "").strip()))


def is_local_command_content(content):
    """Return True only when every non-empty part is local-command text."""
    if isinstance(content, str):
        return is_local_command_text(content)
    if not isinstance(content, list):
        return False
    texts = []
    for item in content:
        if isinstance(item, str):
            if item.strip():
                texts.append(item)
            continue
        if not isinstance(item, dict) or item.get("type") not in ("text", None):
            return False
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return bool(texts) and all(is_local_command_text(text) for text in texts)


def is_config_command_messages(messages):
    """Recognize Claude's interactive ``/config`` AskUserQuestion flow."""
    if not messages:
        return False
    first_role, first_content = messages[0]
    if first_role != "user" or not isinstance(first_content, str):
        return False
    if first_content.strip().lower() not in ("config", "/config"):
        return False

    ask_user_question = 0
    for role, content in messages[1:]:
        if not isinstance(content, list):
            return False
        for item in content:
            if not isinstance(item, dict):
                return False
            block_type = item.get("type")
            if role == "assistant":
                if block_type == "thinking":
                    continue
                if block_type == "tool_use" and item.get("name") == "AskUserQuestion":
                    ask_user_question += 1
                    continue
                return False
            if role == "user" and block_type in ("tool_result", "text"):
                continue
            return False
    return ask_user_question > 0


def is_legacy_local_command_markdown(text, source):
    """Recognize an old command-only Markdown without hiding real chats.

    A match requires a Claude/Cowork file with at least one user turn, no
    assistant turn, and every user turn beginning with a known local-command
    wrapper. A real conversation that merely quotes one of these tags does not
    match because it contains other user or assistant content.
    """
    if str(source or "").strip().lower() not in ("claude-code", "cowork"):
        return False
    turns = MARKDOWN_TURN.findall(text or "")
    if not turns:
        return False
    if CONFIG_TITLE.search(text or ""):
        first_speaker, first_body = turns[0]
        assistant_bodies = [body.strip() for speaker, body in turns if speaker.lower() == "claude"]
        if (
            first_speaker.lower() != "claude"
            and first_body.strip().lower() in ("config", "/config")
            and assistant_bodies
            and all(CONFIG_TOOL_BODY.fullmatch(body) for body in assistant_bodies)
        ):
            return True
    user_turns = []
    for speaker, body in turns:
        if speaker.lower() == "claude":
            return False
        user_turns.append(body.strip())
    return bool(user_turns) and all(is_local_command_text(turn) for turn in user_turns)


def strip_local_command_markdown_turns(text, source):
    """Remove generated local-command turns from an in-memory Markdown view.

    The cumulative Markdown file remains untouched. Readers and derived metrics
    use this cleaned representation so local UI traffic does not look like user
    intent or enter model-review context.
    """
    if str(source or "").strip().lower() not in ("claude-code", "cowork"):
        return text or ""

    def replace(match):
        speaker, body = match.group(1), match.group(2)
        if speaker.lower() != "claude" and is_local_command_text(body):
            return "\n"
        return match.group(0)

    return MARKDOWN_TURN.sub(replace, text or "")
