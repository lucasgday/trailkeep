---
name: trailkeep-project-review
description: Use when configuring or running trailkeep's optional coding-agent generative review layer from a local _review_run_plan.json. Handles post-backup project review automation, selected-context model calls, generated sidecars, approval flags, and deterministic generated-output evals.
---

# Trailkeep Project Review

Use this skill only for trailkeep's optional generative layer. trailkeep's backup
scripts and viewer stay local and zero-network; model calls happen only through
the user's coding agent when the user has enabled this layer.

Treat model calls as remote unless the agent can prove the model is local or
on-device. Send only context selected by `_review_run_plan.json` unless the user
approves a wider deep-review scope. Never send secrets, API keys, tokens,
credentials, private env files, unrelated repo data, or the full backup folder as
an unscoped dump.

If the recurring automation uses a remote or unproven-local provider, get user
approval once during setup with the schedule, scope, provider, model/alias,
local output files, and remote-context risk. Do not ask again on every daily run
merely because the provider is remote; pause only when the gate requires
approval for `requires_approval` / `possible_secret`, or when provider/model,
scope, schedule, or output files materially change.

## Inputs

Resolve:

- `trailkeep_repo`: the local repo containing `docs/generative-layer.md`.
- `backup_dir`: the backup folder containing `markdown-*` folders and
  `_review_run_plan.json`.

If either path is ambiguous, ask before reading project context or calling a
model.

## Source Of Truth

Read `<trailkeep_repo>/docs/generative-layer.md` before running a review. Follow
it for sidecar schemas, source precedence, privacy rules, flag handling,
checkpoints, model tier intent, and daily/manual sequences.

Use `<trailkeep_repo>/docs/prompts.md` for the canonical user-facing setup,
manual review, and approval-intervention prompt text when a prompt needs to be
shown or copied.

Do not duplicate the full spec in prompts or sidecars. The repo spec is the
contract; this skill is the runtime workflow.

## Runtime Workflow

Recurring trailkeep review runs should use a dedicated coding-agent automation
thread or subagent. Use the main/user-visible thread only for setup approval and
intervention prompts.

1. Read `<backup_dir>/_review_run_plan.json`.
2. Read `<backup_dir>/_review_eval_report.json`.
3. Before any model call, run the bundled gate:

```sh
python3 <skill_dir>/scripts/pre_model_gate.py --backup-dir <backup_dir>
```

Exit code `0` means model calls may proceed. Exit code `1` means planner evals
or required files failed, including stale/mismatched plan/eval files or a
missing/stale `backup_dir/log.json` latest backup run. Exit code `2` means user
approval is required. In both nonzero cases, stop before model calls.

4. If approval is required, open or resume the coding-agent thread and ask the
   user once with the full approval batch from the gate output. Use only
   sanitized project names and input ids. Never print suspected secret values.
   Do not ask project-by-project. If this agent cannot open/resume a thread, use
   its closest supported user-intervention surface. Do not continue model calls
   until the user explicitly approves inputs, excludes inputs, or stops the run.
   Record that choice in `<backup_dir>/_review_gate_decisions.json`, scoped to
   the current plan `generated_at` and input content hashes, then rerun the gate.
   `needs_approval` is a transient pause; it is not a permanent blocker.
5. After the gate exits `0`, use `<backup_dir>/_review_effective_plan.json` if
   present. It contains the selected context after approval/exclusion decisions.
   Excluded inputs must not be sent to the model.
6. Use only the selected inputs from the effective plan, plus extra context
   explicitly allowed by a deep-review flow.
7. Default daily runs are incremental: use previous sidecars, repo
   planning/design docs, and only new or changed conversations. Full raw
   conversation reads are allowed only for explicit bootstrap/deep-review modes,
   scoped to the project being reviewed unless the user approves a global
   full-archive pass.
8. Write generated sidecars only at the root of `backup_dir`:
   `_conversation_summaries.json`, `_project_reviews.json`,
   `_agent_profile.json`, and `_review_update_log.json`.
9. After writing sidecars, run the bundled finalizer:

```sh
python3 <skill_dir>/scripts/finalize_review_run.py --trailkeep-repo <trailkeep_repo> --backup-dir <backup_dir>
```

The finalizer runs trailkeep's generated-output evals, writes
`_review_generated_eval_report.json`, appends the review run to
`_review_update_log.json`, validates the log, and exits nonzero if the run must
not be considered `ok`.

The skill must not reimplement generated-output checks in prompts or ad hoc
logic. Those checks live in
`<trailkeep_repo>/converters/eval_generated_reviews.py`; the finalizer calls
that repo runner and records the result in `_review_update_log.json`.

## Sidecar Responsibilities

- `_conversation_summaries.json`: update only new or changed conversations by
  session id and preserve existing entries.
- `_project_reviews.json`: use repo planning/design docs as source of truth,
  conversation summaries as evidence, preserve stable task ids, preserve the
  user's roadmap/backlog priority order, and make suggested next steps advance
  the existing roadmap when present. If conversations reveal new legitimate work
  not present in the roadmap, add it as a pending/candidate task or open
  question with evidence; do not silently promote it above existing roadmap
  priorities.
- Cumulative review means using previous sidecars and checkpoints as compact
  memory, sending only selected deltas to the model by default, preserving stable
  ids/notes, and escalating to broader review only for bootstrap, explicit
  manual deep-review, deterministic broad/conflicting changes, low confidence,
  evidence-backed stale checkpoints, or major metadata changes. Time passing
  alone is not a reason to reread the full project.
- For each project: compare current sessions, repo docs, metadata, git state,
  and deploy state against `_project_reviews.json` checkpoints; skip unchanged
  projects; for small conversation-only changes, send the previous compact
  review plus the new/changed conversation evidence only; run broader review or
  set a deep-review flag only when deterministic change signals or low
  confidence show the prior project summary may be stale; preserve task ids
  unless evidence says to update, close, split, or replace them.
- Keep runs token-efficient: use cheaper configured tiers for classification and
  summarization, and stronger tiers only for deep project review or
  design-system extraction.
- Daily design-system review is incremental: skip projects without UI/design
  changes; use `design.md`, `docs/design.md`, `docs/design-patterns.md`, and
  component files as source of truth; use new conversations only as evidence;
  update the design-system summary only with new evidence; set
  `needs_deep_design_review: true` for broad or conflicting changes instead of
  rereading the full project automatically.
- `_agent_profile.json`: update recurring preferences, working style, repo
  conventions, and prompt patterns from compact project reviews.
- `_review_update_log.json`: record the automation result, provider/routing
  metadata when known, concrete `model_used`, affected projects, outputs, eval
  report path, and errors.
  Keep it as one global chronological log in `backup_dir`; do not create
  per-project review logs unless trailkeep later needs them for size or
  performance.

Do not write generated sidecars into project repos, source-tool raw folders,
`markdown-*` folders, or the trailkeep repo. Do not commit private backups or
generated sidecars.

Never transmit the entire backup folder as an archive or unscoped dump. The
review plan is the input manifest: project, files/session ids selected, reason,
estimated tokens, and model tier.

## Scheduling

Prefer a true post-backup trigger if the user's coding agent supports it. If the
agent can only schedule by time, infer the daily trailkeep backup/update time
from the installed launchd/cron job or recent `backup_dir/log.json` entries, and
schedule the review 10-15 minutes later. The pre-model gate still validates that
the plan/eval are current and aligned, and that the latest backup run in
`log.json` is less than 24 hours old before any model call.

## Model Routing

Use one skill with modes, not one skill per model. If the agent supports model
routing, map the spec's `cheap`, `default`, and `strong` tiers to the user's
configured models. If per-task routing is unavailable but the automation can
choose one model, configure that automation to use the `strong` tier by default.
If the agent cannot choose a model at all, continue with the available model,
write `model_routing: "unavailable"` in `_review_update_log.json`, and still
record `model_used` with the concrete model name, configured alias, or
`"unknown"` if the agent/provider hides it.
