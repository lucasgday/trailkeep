# Canonical Prompts

These are the canonical user-facing prompts for trailkeep's optional generative
layer.

`docs/generative-layer.md` remains the source of truth for architecture, privacy,
schemas, sidecar contracts, model routing, evals, and automation rules. This file
only canonizes the prompts users copy into their coding agent.

The viewer is a standalone offline HTML file, so it embeds copies of these
prompts instead of loading this file at runtime. When changing prompt text, keep
these locations synchronized:

- `viewer.html`
- `docs/index.html`
- `docs/prompts.md`

## Initial Setup

Use this once to install or link the shared skill and configure the coding-agent
automation that runs after trailkeep's normal backup.

```text
Set up the optional trailkeep generative layer in my coding agent.

Context:
- trailkeep itself stays local and never makes network calls. The backup scripts and viewer never send data.
- This optional review layer is agent-powered and runs inside my coding agent after the normal trailkeep backup.
- If this agent uses a remote model provider, selected project context may be sent to that provider as part of the review.
- If this agent cannot prove the model is local/on-device, treat it as remote.
- Only send context selected by _review_run_plan.json unless I explicitly approve a wider deep-review scope.
- Remote-provider approval happens once during setup. Daily runs should not ask again merely because the provider is remote; they should ask only when _review_run_plan.json sets requires_approval or possible_secret, or when provider/model, scope, schedule, or output files materially change.
- Do not send secrets, API keys, tokens, credentials, private env files, or unrelated repo data.
- Do not add model calls to update-backup.sh or viewer.html.

Source of truth:
- In the local trailkeep repo, read docs/generative-layer.md and follow it exactly.
- Read skills/trailkeep-project-review/SKILL.md and use its bundled finalizer.
- If you cannot find docs/generative-layer.md, ask me for the trailkeep repo path before continuing.

Your tasks:
1. Resolve backup_dir as the folder containing markdown-* folders and the _review_run_plan.json you will consume.
2. Install or link the shared trailkeep-project-review skill from the repo if this agent supports local skills.
3. Resolve skill_dir as the installed skill path, or fallback to <trailkeep_repo>/skills/trailkeep-project-review.
4. Before installing or enabling any recurring job that may call a remote or unproven-local model, show me the schedule, scope, provider/model tier, concrete model name or alias when known, estimated tokens to be processed, local files it will write, and that selected context may be sent to the provider. Wait for approval once.
5. Create a recurring review automation owned by this coding agent. Prefer a true post-backup trigger if this agent supports it. If only time-based scheduling is available, infer the daily trailkeep backup/update schedule from the installed launchd/cron job or recent backup_dir/log.json entries, then schedule the review 10-15 minutes after that update normally runs.
6. Create or use a dedicated coding-agent automation thread/subagent for recurring trailkeep review runs. Use the main/user-visible thread only for setup approval and intervention prompts.
7. Before any model call, read backup_dir/_review_run_plan.json and backup_dir/_review_eval_report.json.
8. Run python3 <skill_dir>/scripts/pre_model_gate.py --backup-dir <backup_dir>. It must validate that the plan/eval are current and aligned, and confirm backup_dir/log.json has a latest backup run less than 24 hours old. Continue to model calls only if it exits 0.
9. If pre_model_gate exits 2, open or resume this coding-agent thread and ask me once with the full approval batch from the gate output. Use only sanitized project names and input ids. Do not ask project-by-project, and do not continue model calls until I choose. Do not ask on a daily run only because the provider is remote if the setup approval was already granted.
10. After I approve, exclude, or stop, write that choice to backup_dir/_review_gate_decisions.json scoped to the current plan generated_at and input content_hashes, then rerun pre_model_gate.py. Do not edit _review_run_plan.json. needs_approval is a transient pause, not a permanent blocker.
11. When pre_model_gate exits 0, use backup_dir/_review_effective_plan.json for model context if it exists. Excluded inputs must not be sent to the model.
12. Default daily runs are incremental: use previous sidecars, repo planning/design docs, and only new or changed conversations.
13. Full raw conversation reads are allowed only for explicit bootstrap/deep-review modes, scoped to the project being reviewed unless I approve a global full-archive pass.
14. Make this cumulative and token-efficient:
   - Do not re-review unchanged projects.
   - Store per-project checkpoints, reviewed session ids, hashes, and last reviewed git commit.
   - Send only new or changed project context to the model by default.
   - Use cheaper model tiers for classification/summarization and stronger models only for deep project review or design-system extraction.
   - Preserve stable task ids and previous conclusions unless new evidence changes them.
15. Cumulative means: preserve checkpoints/fingerprints by project, reuse previous summaries/reviews as compact memory, send only selected deltas by default, preserve stable task ids and notes, and run broader review only for bootstrap, explicit deep-review, broad/conflicting changes, low confidence, stale checkpoints, or major metadata changes.
16. Never re-read the full project just because time passed. A stale checkpoint needs evidence, not age alone.
17. For each project: compare current sessions, repo docs, metadata, git state, and deploy state with _project_reviews.json checkpoints; skip if unchanged; for small conversation-only changes, send previous compact review plus new/changed conversation evidence only; run broader review only when deterministic change signals or low confidence show the prior project summary may be stale; preserve task ids unless evidence says to update, close, split, or replace them.
18. Respect requires_approval, possible_secret, needs_deep_review, and needs_deep_design_review exactly as described in docs/generative-layer.md.
19. Write generated sidecars only at the root of backup_dir:
   - _conversation_summaries.json
   - _project_reviews.json
   - _agent_profile.json
   - _review_update_log.json
20. After writing sidecars, run: python3 <skill_dir>/scripts/finalize_review_run.py --trailkeep-repo <trailkeep_repo> --backup-dir <backup_dir> --model-provider <provider_or_agent> --model-routing <available_or_unavailable> --model-used <concrete_model_or_alias_or_unknown>
21. If the finalizer fails, do not mark the review run ok. Use _review_generated_eval_report.json and _review_update_log.json as the evidence.
22. Do not write generated sidecars into project repos, source-tool raw folders, markdown-* folders, or the trailkeep repo.
23. Never transmit the entire backup folder as an archive or unscoped dump. Use the _review_run_plan.json input manifest first.
24. Do not commit private backups or generated sidecars.

After setup, report:
- skill install path or fallback;
- automation schedule/trigger, including derived backup time and review offset if time-based;
- backup_dir;
- model tier routing availability and concrete model used or model alias;
- sidecars that will be written;
- unresolved approvals or decisions.
```

## Manual Project Review

Use this only when refreshing one project immediately instead of waiting for the
daily post-backup automation. The viewer fills the placeholders with the
selected project's metadata, ledger stats, and recent backed-up conversations.

```text
Update the incremental trailkeep review for this project.

Project: <project_name>

Known facts:
- path: <project_path_or_virtual>
- repo: <repo_url_or_none>
- git: <branch_commit_dirty_or_none>
- stack: <detected_stack_or_none>
- status: <active_inactive_gone_or_unknown>
- conversations: <conversation_count>

Activity:
<ledger_activity>

Recent backed-up conversations:
<recent_conversation_list>

Instructions:
- Follow docs/generative-layer.md from the local trailkeep repo if available.
- Follow skills/trailkeep-project-review/SKILL.md if the repo skill is available.
- Resolve backup_dir as the folder containing markdown-* folders and the _review_run_plan.json for this run. If ambiguous, ask.
- Resolve skill_dir as the installed trailkeep-project-review skill path, or fallback to <trailkeep_repo>/skills/trailkeep-project-review.
- Before any model call, run python3 <skill_dir>/scripts/pre_model_gate.py --backup-dir <backup_dir>. It also confirms the plan/eval are current and aligned, and backup_dir/log.json has a latest backup run less than 24 hours old. Continue only if it exits 0.
- If the gate exits 2, resolve approval through _review_gate_decisions.json, rerun the gate, and then use _review_effective_plan.json for model context.
- Write generated sidecars only at the root of backup_dir, especially backup_dir/_project_reviews.json.
- After writing sidecars, run python3 <skill_dir>/scripts/finalize_review_run.py --trailkeep-repo <trailkeep_repo> --backup-dir <backup_dir>.
- If the finalizer fails, do not mark the review run ok.
- Do not write generated sidecars into project repos, source-tool raw folders, markdown-* folders, or the trailkeep repo.
- First inspect the local repo if it exists.
- If ROADMAP.md, BACKLOG.md, TODO.md, docs/product-progress.md, docs/project-progress.md, docs/agent-handoff.md, docs/design-patterns.md, docs/design.md, design.md, AGENTS.md with continuity/product instructions, local issues/configs, or equivalents exist, treat those files as the source of truth.
- For next step, roadmap, and tasks, roadmap/backlog/product-progress win. For design-system extraction, design docs and real component files win. Conversations only explain recent decisions or undocumented changes.
- Preserve the user's existing priority/order from roadmap/backlog files. Suggested next steps should advance the existing roadmap when present.
- If conversations reveal new legitimate work not present in the roadmap, add it as a pending/candidate task or open question with evidence. Do not silently promote it above the existing roadmap priorities.
- Run design-system review daily, but incrementally: skip projects without UI/design changes; use design docs and component files as source of truth; use new conversations only as evidence for changes or undocumented decisions; update design_system only with new evidence; set needs_deep_design_review=true for broad or conflicting changes instead of rereading the full project automatically.
- Use these conversations as supporting evidence for recent decisions, completed work, and blockers.
- Do not re-read everything if unnecessary: compare against _project_reviews.json and process only deltas.
- Update or create this project's entry in _project_reviews.json.
- Preserve stable task ids unless there is clear evidence.
- If there are contradictions, add them to open_questions.
- If context is insufficient, set needs_deep_review or needs_deep_design_review instead of inventing.

Return/write only the updated JSON entry for this project, compatible with the backup_dir/_project_reviews.json sidecar.
```

## Approval Intervention

Use this shape when `pre_model_gate.py` exits `2`. Do not show raw conversation
text, suspected secret values, or unscoped backup contents.

```text
Trailkeep needs your approval before this generative review can call a model.

I have not sent any project context to a model yet.

Reason:
- requires_approval or possible_secret was set in _review_run_plan.json.

Flagged inputs:
<sanitized_input_ids_from_pre_model_gate>

Choose one:
- approve this run as planned;
- exclude specific input ids and rerun the gate;
- stop this review run.

After you choose, I will write `_review_gate_decisions.json` for the current plan and rerun the gate. I will continue only after the gate exits 0 and will use `_review_effective_plan.json` for model context.
```
