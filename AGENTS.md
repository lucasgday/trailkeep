# AGENTS.md

Context for AI agents (and humans) working on **trailkeep** — a local, self-hosted
backup + viewer for your AI-coding-tool conversations (Claude Code, Codex, Cursor,
OpenCode, Cowork). macOS and Linux (paths resolved per-OS; Cowork is macOS-only).

## Non-negotiable rules

1. **Privacy is the product. The viewer makes ZERO network calls.** Never add
   `fetch`, `XMLHttpRequest`, `sendBeacon`, WebSockets, analytics/telemetry, or
   external resources (no CDN scripts/fonts) to `viewer.html`. The scripts only
   read local files and write local Markdown. Nothing — raw or derived — may leave
   the user's machine. This is the whole pitch; don't break it.
2. **English only in code** — comments and identifiers. Two deliberate exceptions,
   do NOT "fix" them:
   - the `es:` block of the `I18N` dictionary in `viewer.html` (the Spanish UI
     translation), and
   - **legacy Spanish data keys** the parser accepts for backward-compat with
     older backups: `fecha/proyecto/fuente/archivada` and the turn/tool markers
     `Tú/herramienta/resultado`, plus `generado/conversaciones`. Keep these.
3. **Cumulative, never destructive.** The backup never deletes already-generated
   markdowns, even if the source tool removed the original.

## Layout

- `update-backup.sh` — orchestrator / CLI entrypoint (`--help`, `--only`,
  `--dry-run`, optional `[OUTPUT_DIR]`). Default data location is
  `~/trailkeep-backups`; `install-auto.command` remembers overrides in
  `~/.config/trailkeep/backup_dir` (or `$XDG_CONFIG_HOME`). Reads each source,
  calls the converters.
  **Loud health detection:** these tools store conversations in private, undocumented
  locations/formats, so a vendor moving a folder or changing a format must never fail
  silently. `run_convert` warns if a converter errors or — given new/changed raw —
  converts 0 sessions; `warn_missing` warns when a source folder is gone but markdowns
  exist for it. Warnings are tallied (`HEALTH_WARN`), summarized at the end, and added
  to the desktop notification. Existing markdowns are never lost (rule #3); the risk it
  guards is NEW data silently not being captured.
- `converters/convert_*.py` — one per source (claude/codex/opencode/cursor; cowork
  reuses convert_claude). Each reads its origin and writes the standard Markdown.
  Codex subagent rollouts remain separate Markdown files for cumulative safety;
  optional `parent_id` / `agent_*` metadata lets the viewer nest them inside the
  parent conversation without duplicating or rewriting the child's content.
  Child identity always comes from the first `session_meta`. Replayed parent
  context is cut at `inter_agent_communication_metadata`, or conservatively at
  the last `task_started` when a markerless rollout contains a different parent
  `session_meta`. Never fall back to parsing that replay from line 1. A recognized
  in-progress child with no child-authored turns is reported as deferred (healthy
  and retried when its file grows); a completed unreadable child remains a loud
  health warning.
- `converters/extract_ledger.py` — **Evidence Ledger**: deterministic, $0, on-device
  metrics (token usage by model, tool/test/build counts, files modified, errors)
  read from each tool's RAW storage. One scanner per format (claude+cowork .jsonl,
  codex rollouts, opencode/cursor SQLite); all emit the same per-session dict.
  Cursor carries no tokens → counts only. **Markdown fallback:** the tools prune old
  raw transcripts, but the `.md` backup is cumulative — so for sessions whose raw is
  gone, counts are parsed from the `.md` (tokens/model only exist in raw). Each
  source writes a per-source `_ledger.json` (the viewer reads every one and
  aggregates). No LLM, no network.
  Incremental: per-session metrics are cached in `_ledger-cache.json` (validated by
  size:mtime) — file sources re-scan only changed sessions; DB sources re-scan only
  when the DB changed. **Cumulative + portable (rule #3):** a session stays in the
  ledger as long as its `.md` exists; metrics measured from raw are carried forward
  from the cache, so token data persists in the data folder and travels with the
  markdowns even after the tool prunes the raw. Called from each source's block in
  `update-backup.sh`. The Claude scan reads multiple raw roots (os.pathsep-joined)
  and dedups by session uuid; `TRAILKEEP_CLAUDE_RAW_EXTRA` points at recovered-raw
  archive folders — read once to seed token data, optional thereafter.
- `converters/extract_projects.py` — **Project metadata**: deterministic, $0,
  on-device. Reads each project's `cwd` from the raw, then its git branch / last
  commit, detected stack (manifests/source hints) and status (active/inactive/gone by
  last-30-days activity or deployed state), plus safe local `repo_url` /
  `deploy_url` hints when available.
  Writes a `_projects.json` sidecar the viewer joins with the ledger (by project
  name) to render a project home. Local reads only (git, manifests/source/deploy
  hints); no network.
  Cowork runs in throwaway sandboxes with random Docker-style `cwd`s, so it folds
  into one **virtual** "cowork" project (no filesystem facts, never "gone"),
  matching the converter which tags every Cowork session `project: cowork`.
- `converters/plan_reviews.py` — **Review preflight plan**: deterministic, $0,
  on-device. Reads Markdown backups plus `_projects.json`,
  `_conversation_summaries.json` and `_project_reviews.json` when present, then
  writes `_review_run_plan.json` with selected inputs, token estimates, safety
  flags and expected local output sidecars for the optional coding-agent
  review layer. When possible secrets are detected in selected conversations or
  repo docs, it writes deterministic redacted text to
  `_review_preprocessed_inputs.json` and points the plan at that sanitized input
  instead of requiring raw-context approval by default. No LLM, no network; the
  viewer only reads the sidecars.
- `converters/eval_review_plan.py` — **Review plan evals**: deterministic, $0,
  on-device. Reads `_review_run_plan.json` and writes `_review_eval_report.json`
  with schema, manifest, no-full-dump, privacy, token-estimate,
  source-precedence, incrementality and output-scope checks. No LLM, no network.
- `converters/eval_generated_reviews.py` — **Generated review evals**:
  deterministic, $0, on-device. Runs after the optional coding-agent automation
  writes `_conversation_summaries.json`, `_project_reviews.json`,
  `_agent_profile.json`, and `_review_update_log.json`. Writes
  `_review_generated_eval_report.json` with schema, referential-integrity,
  checkpoint, task-id, privacy, source-precedence, evidence-grounding,
  tool-evidence, instruction-context, actionability, semantic-quality, and update-log checks. Nonzero
  exit means the automation must not mark the run `ok`.
- `skills/trailkeep-project-review/` — repo-versioned optional coding-agent
  skill. `SKILL.md` defines the runtime workflow;
  `scripts/run-project-review-agent-gates.sh` is the mandatory wrapper the
  optional automation should call for `pre`, `repo-sync`, `validate-summary`,
  and `finalize`;
  `scripts/pre_model_gate.py` blocks model calls when planner evals fail,
  writes partial safe `_review_effective_plan.json` files when only some
  projects need approval, reads `_review_gate_decisions.json` to resolve
  approval/exclusion choices for the current plan, and writes
  `_review_effective_plan.json` as the selected context that model calls may
  use; `scripts/validate_conversation_summary.py` validates each generated
  conversation summary before checkpointing; `scripts/check_repo_sync.py` runs
  the optional post-gate local git
  freshness check and writes `_review_repo_sync.json`; `scripts/finalize_review_run.py`
  runs generated-output evals, appends `_review_update_log.json`, reruns evals
  so the log is validated, and exits nonzero unless the generated review run can
  be treated as `ok`.
- `viewer.html` — standalone, bilingual (EN/ES) viewer. Pure reader. No build
  step. It reads optional local generative sidecars when present:
  `_conversation_summaries.json` in conversation detail, `_project_reviews.json`
  in Project Home, `_agent_profile.json` in Analytics, and
  `_review_update_log.json` in Runs plus affected Project Homes. It never
  generates those files and never calls a model. Conversation loading is limited
  to `markdown-*` paths with trailkeep identity metadata and recognized turns.
  When supported, the local viewer persists an approved directory handle in
  IndexedDB; the hosted demo must not auto-open personal folders.
- `*.command` — double-click launchers (install/uninstall the launchd task; run).
- `docs/` — `index.html` (the GitHub Pages live demo, sample data baked in),
  screenshots, `hero.gif`, and `generative-layer.md` (the stable contract for
  the optional coding-agent review layer).
- `ROADMAP.md` — public roadmap. `ROADMAP.private.md` — maintainer-only strategy &
  full vision (gitignored via `*.private.md`; not in clones).

## Standard Markdown format (converters ↔ viewer contract)

Converters emit, and the viewer parses, exactly this:

```
# <title>

<!-- date: <ISO> | id: <id> | project: <project> | source: <source> | archived: <true|false> -->

### You

…

### <Assistant>      (Claude / Codex / Cursor / OpenCode)

…
```

Tool calls render as `[tool: <name> → …]` / `[result]` blocks. If you change the
format, update **both** the converters and the viewer's parser, and keep reading
the legacy Spanish keys (rule 2).

Codex subagents may append `format_version`, `parent_id`, `agent_path`,
`agent_nickname`, `agent_depth`, `agent_status`, and `completed_at` to the same
metadata comment. These fields are optional; older and non-Codex Markdown keeps
the base contract above. A `spawn_agent` tool marker anchors the child in the
parent timeline, while an unmatched child still renders through the viewer's
related-subagents fallback.

## Adding a source

Write a `converters/convert_<tool>.py` that reads that tool's storage and emits the
format above, then wire a block into `update-backup.sh`. The viewer needs no
changes. See any existing converter as a reference.

## Verifying changes

- Shell: `bash -n update-backup.sh *.command scripts/run-project-review-agent-gates.sh`
- Converters/skills: `python3 -m py_compile converters/atomic_io.py converters/convert_*.py converters/extract_ledger.py converters/extract_projects.py converters/plan_reviews.py converters/eval_review_plan.py converters/eval_generated_reviews.py skills/trailkeep-project-review/scripts/pre_model_gate.py skills/trailkeep-project-review/scripts/validate_conversation_summary.py skills/trailkeep-project-review/scripts/check_repo_sync.py skills/trailkeep-project-review/scripts/prepare_review_test.py skills/trailkeep-project-review/scripts/finalize_review_run.py`
- Generated review eval fixtures: `node scripts/test-generated-review-evals.cjs`
- Backup retry transaction: `node scripts/test-backup-retry.cjs`
- Codex subagent hierarchy: `node scripts/test-codex-subagents.cjs`
- Viewer JS parses: `node -e "const h=require('fs').readFileSync('viewer.html','utf8');new Function(h.match(/<script>([\s\S]*)<\/script>/)[1]);console.log('ok')"`
- Prompt drift: `node scripts/check-prompt-drift.cjs`
- Viewer Playwright QA (optional dev check, not used by backup):
  `node scripts/verify-viewer.cjs`
- Visual: serve a folder of sample `.md` and open the viewer headless, or open
  `viewer.html` and point it at a markdown folder. The viewer must render with no
  console errors and make no network requests.

## i18n

UI strings live in the `I18N` dictionary (`en`/`es`) in `viewer.html`; use `t(key)`
(or `T(key)` inside turn loops where `t` is shadowed). Add new strings to **both**
languages. Language auto-detects from the browser and is user-toggleable.

## Roadmap

See [ROADMAP.md](ROADMAP.md). Post-launch direction (Linux vs the summary/AGENTS.md
pipeline) is feedback-driven; details and strategy are in the maintainer's private
notes.
