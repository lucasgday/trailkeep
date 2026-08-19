#!/usr/bin/env python3
"""Project metadata — deterministic, $0, on-device.

Maps each project (by its working-directory basename) to its filesystem facts:
git branch + last commit, detected stack, and whether the directory still exists.
The viewer joins this with the per-project ledger metrics to render a project home.

The viewer is a pure reader (no shell/git), so the backup computes this and writes a
`_projects.json` sidecar next to the markdowns. No network: only local reads of the
project dirs (git, manifest/source/deploy hints) and raw transcripts (for the cwd,
activity, and explicit production deploy evidence).

Usage: extract_projects.py <out_dir> [claude=<dir>] [cowork=<dir>] [codex=<dir>] [opencode=<db>]
  Each source is scanned for the project working directory, latest conversation
  activity, and explicit production deploy URLs. Cursor is skipped — its store
  carries no project path.
"""
import json, os, re, sys, glob, subprocess, datetime
from urllib.parse import urlsplit, urlunsplit

from claude_internal import is_config_command_messages, is_local_command_content
from codex_internal import is_guardian_source, latest_timestamp

# Manifest file -> stack label. First match(es) win; a project can have several.
MANIFESTS = [
    ("package.json", "node"), ("deno.json", "deno"), ("tsconfig.json", "typescript"),
    ("pyproject.toml", "python"), ("requirements.txt", "python"), ("setup.py", "python"),
    ("Cargo.toml", "rust"), ("go.mod", "go"), ("Gemfile", "ruby"),
    ("pom.xml", "java"), ("build.gradle", "java"), ("composer.json", "php"),
    ("Package.swift", "swift"), ("pubspec.yaml", "dart"), ("Dockerfile", "docker"),
]
# Fallback source hints for lightweight repos that do not carry manifests.
SOURCE_HINTS = [
    ((".html", ".htm"), "html"),
    ((".py",), "python"),
    ((".sh", ".command"), "shell"),
    ((".ts", ".tsx"), "typescript"),
    ((".js", ".jsx", ".mjs", ".cjs"), "node"),
    ((".rs",), "rust"),
    ((".go",), "go"),
    ((".swift",), "swift"),
    ((".rb",), "ruby"),
    ((".java",), "java"),
    ((".php",), "php"),
]
STACK_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__"}
# Hints that a project is deployed somewhere (local read, no network).
DEPLOY_HINTS = ["vercel.json", "netlify.toml", "fly.toml", ".github/workflows",
                "Procfile", "render.yaml", "wrangler.toml"]
DEPLOY_TEXT_HINTS = [
    "README.md", "README.mdx", "README.es.md", "BACKLOG.md", ".env.example",
    os.path.join("docs", "deployment.md"),
    os.path.join("docs", "agent-handoff.md"),
    os.path.join("docs", "product-progress.md"),
]
DEPLOY_PLATFORM_HOSTS = (
    "vercel.app", "netlify.app", "fly.dev", "pages.dev", "workers.dev",
    "onrender.com", "render.com",
)
NON_DEPLOY_HOSTS = {
    "github.com", "gitlab.com", "bitbucket.org", "localhost", "127.0.0.1",
    "0.0.0.0", "schema.org", "json-schema.org", "openapi.vercel.sh",
    "vercel.com", "netlify.com", "render.com", "fly.io", "cloudflare.com",
    "supabase.com", "resend.com", "tally.so", "discord.com", "x.com",
    "twitter.com", "linkedin.com", "mail.google.com", "google.com",
    "docs.github.com", "developer.mozilla.org", "nextjs.org",
}
NON_DEPLOY_TLDS = {
    "db", "json", "lock", "md", "sqlite", "toml", "ts", "tsx", "vscdb",
    "yaml", "yml",
}
PROJECT_TOKEN_STOPWORDS = {
    "app", "web", "site", "api", "server", "admin", "client", "frontend",
    "backend", "service", "repo", "project", "codex",
}
ACTIVE_DAYS = 30
DEPLOY_URL_PATTERN = re.compile(
    r'https?://[^\s"\'<>\)\]]+'
    r'|(?<!@)\b[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s"\'<>\)\]]*)?'
)
PRODUCTION_CONTEXT_PATTERN = re.compile(
    r'\b(?:production|prod|live|public|published|deployed|deployment|release)\b'
    r'|--(?:prod|production)\b',
    re.I,
)
PRODUCTION_COMMAND_PATTERN = re.compile(
    r'\b(?:vercel|netlify|fly|wrangler|deploy)\b[^\n]{0,180}'
    r'--(?:prod|production)\b|--(?:prod|production)\b',
    re.I,
)
PREVIEW_CONTEXT_PATTERN = re.compile(
    r'\b(?:preview|previews|staging|stage|development|dev|testing|test|qa|review)\b'
    r'|\b(?:deploy-preview|branch|feature|feat|pull-request|pr)[-_ ]?\d*\b',
    re.I,
)
PREVIEW_URL_LABELS = {
    "preview", "previews", "staging", "stage", "development", "dev",
    "testing", "test", "qa", "review", "reviews",
}
PREVIEW_URL_PREFIXES = (
    "deploy-preview-", "preview-", "branch-", "feature-", "feat-",
    "pull-request-", "pr-", "git-",
)
PREVIEW_URL_MARKERS = (
    "-preview", "-staging", "-stage", "-development", "-dev", "-testing",
    "-test", "-qa", "-review", "-branch", "-git-",
)
TEXT_FIELDS = (
    "text", "content", "output", "result", "input", "arguments", "command",
    "cmd", "url", "uri", "message", "data", "value",
)


def text_fragments(value):
    """Yield user-visible-ish text fields from a raw message/tool payload."""
    if isinstance(value, str):
        if value.strip():
            yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from text_fragments(item)
        return
    if not isinstance(value, dict):
        return
    if value.get("type") in ("thinking", "reasoning"):
        return
    for key in TEXT_FIELDS:
        if key in value:
            yield from text_fragments(value[key])


def is_preview_url(url):
    """Return True for common preview/staging/development deployment URLs."""
    try:
        parts = urlsplit(url)
    except Exception:
        return False
    labels = [label for label in (parts.hostname or "").lower().split(".") if label]
    host_labels = labels[:-1] if len(labels) > 1 else []
    for label in host_labels:
        if label in PREVIEW_URL_LABELS:
            return True
        if any(label.startswith(prefix) for prefix in PREVIEW_URL_PREFIXES):
            return True
        if any(marker in label for marker in PREVIEW_URL_MARKERS):
            return True
    path_labels = [label for label in parts.path.lower().split("/") if label]
    return any(label in PREVIEW_URL_LABELS for label in path_labels)


def conversation_context(text, start, end):
    """Return the URL's line and a bounded nearby context for classification."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    window_start = max(0, start - 180)
    window_end = min(len(text), end + 180)
    return line, text[window_start:window_end]


def conversation_deploy_candidates(path, evidence):
    """Extract explicit production deployment URLs from raw conversation evidence."""
    if not path or not evidence:
        return []
    production_command_seen = any(
        PRODUCTION_COMMAND_PATTERN.search(text)
        for _timestamp, texts in evidence
        for text in texts
    )
    candidates = []
    ordinal = 0
    for timestamp, texts in evidence:
        for text in texts:
            for match in DEPLOY_URL_PATTERN.finditer(text):
                raw = match.group(0).rstrip(".,;:`'\"")
                url = normalize_http_url(raw)
                if not url or is_preview_url(url):
                    continue
                line, nearby = conversation_context(text, match.start(), match.end())
                if PREVIEW_CONTEXT_PATTERN.search(line):
                    continue
                explicit_production = bool(PRODUCTION_CONTEXT_PATTERN.search(line))
                if not explicit_production:
                    explicit_production = bool(PRODUCTION_CONTEXT_PATTERN.search(nearby))
                if not explicit_production and production_command_seen:
                    explicit_production = is_deploy_platform_host(url_host(url))
                if not explicit_production:
                    continue
                url = url_origin(url)
                score = deploy_url_score(url, path, source_priority=120)
                if score is None:
                    continue
                candidates.append({
                    "url": url,
                    "timestamp": timestamp,
                    "score": score,
                    "ordinal": ordinal,
                })
                ordinal += 1
    return candidates


def select_conversation_deploy_url(candidates):
    """Choose the latest explicit production URL mentioned in conversations."""
    if not candidates:
        return None

    def key(candidate):
        timestamp = str(candidate.get("timestamp") or "").strip()
        try:
            parsed = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return 1, parsed.timestamp(), candidate.get("score", 0), candidate.get("ordinal", 0)
        except (TypeError, ValueError, OverflowError):
            return 0, 0, candidate.get("score", 0), candidate.get("ordinal", 0)

    return max(candidates, key=key)["url"]


def claude_project_activity(path):
    """Return cwd, activity, eligibility, and deploy evidence for a session."""
    cwd = None
    latest_conversation = None
    visible_message_kinds = []
    message_sequence = []
    evidence = []
    for line in open(path, errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if cwd is None and d.get("cwd"):
            cwd = d["cwd"]
        message = d.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role", d.get("type"))
        content = message.get("content")
        message_sequence.append((role, content))
        has_text = isinstance(content, str) and bool(content.strip())
        has_tool_result = False
        has_tool_use = False
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text" and str(block.get("text") or "").strip():
                    has_text = True
                elif block_type == "tool_result":
                    has_tool_result = True
                elif block_type == "tool_use":
                    has_tool_use = True
        assistant_usage = role == "assistant" and bool(message.get("usage"))
        if not (has_text or has_tool_result or has_tool_use or assistant_usage):
            continue
        local_command = (
            role == "user" and has_text and not has_tool_result
            and not has_tool_use and is_local_command_content(content)
        )
        kind = "local" if local_command else "conversation"
        visible_message_kinds.append(kind)
        if kind == "conversation":
            latest_conversation = latest_timestamp(latest_conversation, d.get("timestamp"))
            evidence.append((d.get("timestamp"), list(text_fragments(content))))

    internal = (
        bool(visible_message_kinds)
        and all(kind == "local" for kind in visible_message_kinds)
    ) or is_config_command_messages(message_sequence)
    eligible = "conversation" in visible_message_kinds and not internal
    deploys = conversation_deploy_candidates(cwd, evidence) if eligible else []
    return cwd, latest_conversation, eligible, deploys


def first_cwd_codex(path):
    """Return cwd, activity, internal status, and production deploy evidence."""
    cwd = None
    ts = None
    internal = False
    found_meta = False
    session_id = None
    child = False
    replayed_parent = False
    last_task_started_line = None
    boundary_line = None
    last_line = 0
    for line in open(path, errors="ignore"):
        last_line += 1
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        ts = latest_timestamp(ts, d.get("timestamp"))
        if d.get("type") == "session_meta" and not found_meta:
            p = d.get("payload", {}) or {}
            session_id = p.get("id")
            cwd = p.get("cwd")
            ts = latest_timestamp(ts, p.get("timestamp"))
            internal = is_guardian_source(p.get("source"))
            source = p.get("source") or {}
            thread_spawn = source.get("subagent", {}).get("thread_spawn") \
                if isinstance(source, dict) and isinstance(source.get("subagent"), dict) \
                else None
            child = isinstance(thread_spawn, dict) and bool(thread_spawn.get("parent_thread_id"))
            found_meta = True
        elif child and d.get("type") == "session_meta":
            replay_id = str((d.get("payload", {}) or {}).get("id") or "")
            if replay_id and replay_id != str(session_id or ""):
                replayed_parent = True
        if child and d.get("type") == "event_msg":
            if (d.get("payload", {}) or {}).get("type") == "task_started":
                last_task_started_line = last_line
        if child and d.get("type") == "inter_agent_communication_metadata":
            boundary_line = boundary_line or last_line

    if child and boundary_line is None and replayed_parent:
        boundary_line = last_task_started_line or last_line

    evidence = []
    line_no = 0
    with open(path, errors="ignore") as source:
        for raw in source:
            line_no += 1
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if child and boundary_line is not None and line_no <= boundary_line:
                continue
            if d.get("type") != "response_item":
                continue
            payload = d.get("payload", {}) or {}
            evidence.append((d.get("timestamp"), list(text_fragments(payload))))
    deploys = conversation_deploy_candidates(cwd, evidence) if not internal else []
    return cwd, ts, internal, deploys


def add(projects, cwd, ts, source, name=None, virtual=False):
    """Tally a (cwd, timestamp, source) observation under the project basename.

    `name`/`virtual` let a source override the bucket: Cowork runs in throwaway
    sandboxes with random Docker-style cwds (e.g. /sessions/affectionate-epic-
    pasteur) that are not real projects, so it all folds into one virtual
    "cowork" project with no filesystem facts (matching the markdown converter,
    which tags every Cowork session `project: cowork`)."""
    if not cwd and not virtual:
        return
    name = name or os.path.basename(cwd.rstrip("/")) or cwd
    p = projects.setdefault(name, {
        "paths": {}, "last": None, "sources": set(), "virtual": virtual,
        "conversation_deploys": [],
    })
    if virtual:
        p["virtual"] = True
    elif cwd:
        p["paths"][cwd] = p["paths"].get(cwd, 0) + 1
    p["sources"].add(source)
    p["last"] = latest_timestamp(p["last"], ts)


def add_deploy_evidence(projects, cwd, deploys):
    """Attach raw conversation deploy evidence to the project selected by cwd."""
    if not cwd or not deploys:
        return
    name = os.path.basename(cwd.rstrip("/")) or cwd
    project = projects.get(name)
    if project is not None:
        project.setdefault("conversation_deploys", []).extend(deploys)


def scan_claude(root, source, projects):
    for r, _d, fnames in os.walk(root):
        if os.sep + "subagents" in r + os.sep:
            continue
        for b in fnames:
            if not b.endswith(".jsonl") or b.startswith("agent-") or b == "audit.jsonl":
                continue
            try:
                cwd, ts, eligible, deploys = claude_project_activity(os.path.join(r, b))
            except Exception:
                continue
            if not eligible:
                continue
            if source == "cowork":
                add(projects, None, ts, "cowork", name="cowork", virtual=True)
            else:
                add(projects, cwd, ts, source)
            add_deploy_evidence(projects, cwd, deploys)


def scan_codex(root, projects):
    for f in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        try:
            cwd, ts, internal, deploys = first_cwd_codex(f)
        except Exception:
            continue
        if internal:
            continue
        add(projects, cwd, ts, "codex")
        add_deploy_evidence(projects, cwd, deploys)


def scan_opencode(db, projects):
    import sqlite3
    try:
        con = sqlite3.connect(db)
        rows = con.execute("SELECT id, directory, time_created FROM session").fetchall()
    except Exception:
        return
    for session_id, directory, tc in rows:
        ts = None
        try:
            if tc:
                ts = datetime.datetime.fromtimestamp(int(tc) / 1000, datetime.timezone.utc).isoformat()
        except Exception:
            ts = None
        evidence = []
        try:
            parts = con.execute(
                "SELECT m.data, p.data, p.time_created "
                "FROM message m JOIN part p ON p.message_id=m.id "
                "WHERE m.session_id=? ORDER BY p.time_created",
                (session_id,),
            ).fetchall()
            for message_data, part_data, part_time in parts:
                try:
                    message = json.loads(message_data) if isinstance(message_data, str) else message_data
                    part = json.loads(part_data) if isinstance(part_data, str) else part_data
                except Exception:
                    continue
                if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
                    continue
                part_ts = ts
                try:
                    if part_time:
                        part_ts = datetime.datetime.fromtimestamp(
                            int(part_time) / 1000, datetime.timezone.utc
                        ).isoformat()
                except Exception:
                    pass
                evidence.append((part_ts, list(text_fragments(message)) + list(text_fragments(part))))
        except Exception:
            pass
        add(projects, directory, ts, "opencode")
        add_deploy_evidence(projects, directory, conversation_deploy_candidates(directory, evidence))
    con.close()


def git_info(path):
    if not os.path.isdir(os.path.join(path, ".git")):
        return None
    def g(*args):
        try:
            return subprocess.run(["git", "-C", path, *args], capture_output=True,
                                  text=True, timeout=4).stdout.strip()
        except Exception:
            return ""
    branch = g("rev-parse", "--abbrev-ref", "HEAD")
    last = g("log", "-1", "--format=%cs\t%s")
    date, _, msg = last.partition("\t")
    dirty = bool(g("status", "--porcelain"))
    remote = g("config", "--get", "remote.origin.url")
    return {"branch": branch or None, "last_commit_date": date or None,
            "last_commit_msg": (msg[:120] or None), "dirty": dirty,
            "repo_url": normalize_repo_url(remote)}


def normalize_http_url(value):
    value = (value or "").strip().strip("`").strip('"').strip("'").rstrip("`.,;:)]")
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value[:-4] if value.endswith(".git") else value.rstrip("/")
    if re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/.*)?$", value):
        return "https://" + value.strip("/")
    return None


def url_host(url):
    try:
        return urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]
    except Exception:
        return ""


def url_origin(url):
    try:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return url
        return urlunsplit((parts.scheme, parts.netloc.lower(), "", "", ""))
    except Exception:
        return url


def is_deploy_platform_host(host):
    return any(host == h or host.endswith("." + h) for h in DEPLOY_PLATFORM_HOSTS)


def is_non_deploy_host(host):
    if not host:
        return True
    if host.rsplit(".", 1)[-1] in NON_DEPLOY_TLDS:
        return True
    if host in NON_DEPLOY_HOSTS:
        return True
    return any(host.endswith("." + h) for h in NON_DEPLOY_HOSTS)


def project_tokens(path):
    name = os.path.basename(os.path.abspath(path)).lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", name) if len(t) >= 3]
    return [t for t in tokens if t not in PROJECT_TOKEN_STOPWORDS]


def host_matches_project(host, path):
    compact = re.sub(r"[^a-z0-9]+", "", host.lower())
    return any(t in compact for t in project_tokens(path))


def deploy_url_score(url, path, source_priority=0, require_project_match=False):
    host = url_host(url)
    if is_non_deploy_host(host):
        return None
    is_platform = is_deploy_platform_host(host)
    matches_project = host_matches_project(host, path)
    if require_project_match and not matches_project:
        return None
    score = source_priority
    score += 10 if is_platform else 100
    if matches_project:
        score += 30
    try:
        if urlsplit(url).path in ("", "/"):
            score += 5
    except Exception:
        pass
    return score


def add_deploy_candidate(candidates, path, value, source_priority=0,
                         require_project_match=False, origin_only=False):
    url = normalize_http_url(value)
    if not url:
        return
    if origin_only:
        url = url_origin(url)
    if is_preview_url(url):
        return
    score = deploy_url_score(url, path, source_priority, require_project_match)
    if score is None:
        return
    candidates.append((score, len(candidates), url))


def deploy_urls_from_text(path):
    pattern = re.compile(
        r'https?://[^\s"\'<>)\]]+'
        r'|(?<!@)\b[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s"\'<>)\]]*)?'
    )
    for rel in DEPLOY_TEXT_HINTS:
        fpath = os.path.join(path, rel)
        if not os.path.exists(fpath) or os.path.getsize(fpath) > 300_000:
            continue
        try:
            text = open(fpath, errors="ignore").read()
        except Exception:
            continue
        for m in pattern.finditer(text):
            yield m.group(0).rstrip(".,;:")


def normalize_repo_url(remote):
    remote = (remote or "").strip()
    if not remote:
        return None
    direct = normalize_http_url(remote)
    if direct:
        return direct
    m = re.match(r"git@([^:]+):(.+)$", remote)
    if not m:
        m = re.match(r"ssh://git@([^/]+)/(.+)$", remote)
    if not m:
        return None
    host, repo = m.group(1), m.group(2)
    repo = repo[:-4] if repo.endswith(".git") else repo
    return f"https://{host}/{repo.strip('/')}"


def detect_stack(path):
    out = []
    for fname, label in MANIFESTS:
        if os.path.exists(os.path.join(path, fname)) and label not in out:
            out.append(label)
    if out:
        return out
    seen = set()
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in STACK_SKIP_DIRS and not d.endswith(".egg-info")]
        for fname in files:
            lower = fname.lower()
            for suffixes, label in SOURCE_HINTS:
                if lower.endswith(suffixes):
                    seen.add(label)
                    break
        if len(seen) == len(SOURCE_HINTS):
            break
    for _suffixes, label in SOURCE_HINTS:
        if label in seen and label not in out:
            out.append(label)
    return out


def is_deployed(path):
    return any(os.path.exists(os.path.join(path, h)) for h in DEPLOY_HINTS)


def detect_deploy_url(path, conversation_candidates=None):
    conversation_url = select_conversation_deploy_url(conversation_candidates or [])
    if conversation_url:
        return conversation_url
    candidates = []
    pkg = os.path.join(path, "package.json")
    if os.path.exists(pkg):
        try:
            add_deploy_candidate(candidates, path, json.load(open(pkg)).get("homepage"),
                                 source_priority=80)
        except Exception:
            pass
    vercel = os.path.join(path, "vercel.json")
    if os.path.exists(vercel):
        try:
            data = json.load(open(vercel))
            for key in ("alias", "aliases", "domains"):
                vals = data.get(key)
                if isinstance(vals, str):
                    vals = [vals]
                if isinstance(vals, list):
                    for val in vals:
                        add_deploy_candidate(candidates, path, str(val),
                                             source_priority=90)
        except Exception:
            pass
    for url in deploy_urls_from_text(path):
        add_deploy_candidate(candidates, path, url, source_priority=45,
                             require_project_match=True, origin_only=True)
    vercel_url = detect_vercel_project_url(path)
    if vercel_url:
        add_deploy_candidate(candidates, path, vercel_url, source_priority=15)
    fly = os.path.join(path, "fly.toml")
    if os.path.exists(fly):
        try:
            m = re.search(r'(?m)^\s*app\s*=\s*["\']([^"\']+)["\']', open(fly, errors="ignore").read())
            if m:
                add_deploy_candidate(candidates, path, f"https://{m.group(1)}.fly.dev",
                                     source_priority=20)
        except Exception:
            pass
    wrangler = os.path.join(path, "wrangler.toml")
    if os.path.exists(wrangler):
        try:
            m = re.search(r'https://[^\s"\']+', open(wrangler, errors="ignore").read())
            if m:
                add_deploy_candidate(candidates, path, m.group(0).rstrip(","),
                                     source_priority=70)
        except Exception:
            pass
    if candidates:
        candidates.sort(key=lambda c: (-c[0], c[1]))
        return candidates[0][2]
    return None


def detect_vercel_project_url(path):
    project = os.path.join(path, ".vercel", "project.json")
    if not os.path.exists(project):
        return None
    try:
        data = json.load(open(project))
    except Exception:
        return None
    name = str(data.get("projectName") or "").strip().lower()
    if not re.match(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", name):
        return None
    return f"https://{name}.vercel.app"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out_dir = sys.argv[1]
    srcs = {}
    for a in sys.argv[2:]:
        k, _, v = a.partition("=")
        if v:
            srcs[k] = v

    projects = {}
    if "claude" in srcs and os.path.isdir(srcs["claude"]):
        scan_claude(srcs["claude"], "claude-code", projects)
    if "cowork" in srcs and os.path.isdir(srcs["cowork"]):
        scan_claude(srcs["cowork"], "cowork", projects)
    if "codex" in srcs and os.path.isdir(srcs["codex"]):
        scan_codex(srcs["codex"], projects)
    if "opencode" in srcs and os.path.isfile(srcs["opencode"]):
        scan_opencode(srcs["opencode"], projects)

    now = datetime.datetime.now(datetime.timezone.utc)
    out = {}
    for name, p in projects.items():
        last = p["last"]
        # Virtual projects (Cowork) have no real working directory: never "gone",
        # no git/stack/deploy facts — status is purely by recency.
        if p.get("virtual"):
            status = "inactive"
            if last:
                try:
                    d = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=datetime.timezone.utc)
                    status = "active" if (now - d).days <= ACTIVE_DAYS else "inactive"
                except Exception:
                    pass
            out[name] = {
                "path": None, "exists": None, "status": status, "virtual": True,
                "last_activity": last, "sources": sorted(p["sources"]),
                "git": None, "stack": [], "deployed": False,
                "repo_url": None, "deploy_url": None,
            }
            continue
        # the most-used cwd wins (handles a project opened from a few paths)
        path = max(p["paths"].items(), key=lambda kv: kv[1])[0]
        exists = os.path.isdir(path)
        git = git_info(path) if exists else None
        deploy_url = detect_deploy_url(path, p.get("conversation_deploys")) if exists else None
        deployed = (is_deployed(path) or bool(deploy_url)) if exists else False
        # status: active if touched in the last month or deployed, else inactive;
        # gone if the directory no longer exists.
        status = "gone" if not exists else "inactive"
        if exists and deployed:
            status = "active"
        elif exists and last:
            try:
                d = datetime.datetime.fromisoformat(last.replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=datetime.timezone.utc)
                status = "active" if (now - d).days <= ACTIVE_DAYS else "inactive"
            except Exception:
                pass
        out[name] = {
            "path": path, "exists": exists, "status": status,
            "last_activity": last, "sources": sorted(p["sources"]),
            "git": git, "stack": detect_stack(path) if exists else [],
            "deployed": deployed,
            "repo_url": (git or {}).get("repo_url"),
            "deploy_url": deploy_url,
        }

    doc = {"generated": datetime.datetime.now().astimezone().isoformat(), "projects": out}
    os.makedirs(out_dir, exist_ok=True)
    json.dump(doc, open(os.path.join(out_dir, "_projects.json"), "w"),
              ensure_ascii=False, indent=2)
    actives = sum(1 for v in out.values() if v["status"] == "active")
    print(f"Projects: {len(out)} ({actives} active, "
          f"{sum(1 for v in out.values() if v['exists'])} on disk)")


if __name__ == "__main__":
    main()
