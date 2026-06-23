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
- Remote-provider approval happens once during setup. Daily runs should not ask again merely because the provider is remote; they should ask only when the gate reports unresolved requires_approval, or when provider/model, scope, schedule, or output files materially change. possible_secret inputs with preprocessed_ref are already redacted locally.
- The optional automation may run git fetch in local project repos to check whether remote changes make a review stale. It must never run git pull or modify a worktree without my explicit approval.
- Do not send secrets, API keys, tokens, credentials, private env files, or unrelated repo data.
- Do not add model calls to update-backup.sh or viewer.html.

Source of truth:
- In the local trailkeep repo, read docs/generative-layer.md and follow it exactly.
- Read skills/trailkeep-project-review/SKILL.md and use the mandatory wrapper at scripts/run-project-review-agent-gates.sh.
- If you cannot find docs/generative-layer.md, ask me for the trailkeep repo path before continuing.

Your tasks:
1. Resolve backup_dir as the folder containing markdown-* folders and the _review_run_plan.json you will consume.
2. Install or link the shared trailkeep-project-review skill from the repo if this agent supports local skills.
3. Resolve skill_dir as the installed skill path, or fallback to <trailkeep_repo>/skills/trailkeep-project-review.
4. Resolve review_gate_cmd as <trailkeep_repo>/scripts/run-project-review-agent-gates.sh. Use this wrapper for all pre-model, repo-sync, and finalizer gates. If skill_dir is outside the repo, pass --skill-dir <skill_dir> to the wrapper.
5. Before installing or enabling any recurring job that may call a remote or unproven-local model, or run git fetch in local project repos, show me the schedule, scope, provider/model tier, concrete model name or alias when known, repo remote-check behavior, estimated tokens to be processed, local files it will write, and that selected context may be sent to the provider. Wait for approval once.
6. Create a recurring review automation owned by this coding agent. Prefer a true post-backup trigger if this agent supports it. If only time-based scheduling is available, infer the daily trailkeep backup/update schedule from the installed launchd/cron job or recent backup_dir/log.json entries, then schedule the review 10-15 minutes after that update normally runs.
7. Create or use a dedicated coding-agent automation thread/subagent for recurring trailkeep review runs. Use the main/user-visible thread only for setup approval and intervention prompts.
8. Before any model call, read backup_dir/_review_run_plan.json and backup_dir/_review_eval_report.json.
9. Run <review_gate_cmd> pre --backup-dir <backup_dir>. It must validate that the plan/eval are current and aligned, and confirm backup_dir/log.json has a latest backup run less than 24 hours old. Continue to model calls only if it exits 0. Exit 0 may be partial; use only projects in _review_effective_plan.json.
10. If the wrapper pre command exits 0 with partial=true or pending_projects, continue only with the safe effective plan and surface the pending approval batch as a non-blocking intervention. Do not send skipped projects or inputs to the model. If it reports auto_excluded_secret_inputs, treat those as non-fatal privacy exclusions.
11. If the wrapper pre command exits 2, open or resume this coding-agent thread and ask me once with the full approval batch from the gate output. Use only sanitized project names and input ids. Do not ask project-by-project, and do not continue model calls until I choose. Do not ask on a daily run only because the provider is remote if the setup approval was already granted.
12. After I approve, exclude, or stop, write that choice to backup_dir/_review_gate_decisions.json scoped to the current plan generated_at and input content_hashes, then rerun <review_gate_cmd> pre --backup-dir <backup_dir>. Do not edit _review_run_plan.json. needs_approval is a transient pause, not a permanent blocker.
13. When the wrapper pre command exits 0, use backup_dir/_review_effective_plan.json for model context if it exists. Excluded inputs and skipped projects must not be sent to the model. For any selected input with possible_secret=true and preprocessed_ref, read the redacted text from backup_dir/_review_preprocessed_inputs.json and use that instead of the raw markdown.
14. Before reviewing projects with local git repos, run <review_gate_cmd> repo-sync --backup-dir <backup_dir>. It may run git fetch to update remote-tracking refs, but must never pull or modify worktrees. Use _review_repo_sync.json to mark repo_may_be_stale, sync_uncertain, or needs_deep_review.
15. Run incrementally and cumulatively by default: compare current sessions, repo docs, metadata, git/repo-sync/deploy state with _project_reviews.json checkpoints; reuse previous summaries/reviews as compact memory; process only selected deltas; skip unchanged projects.
16. Do not reread full raw conversations just because time passed. Full raw reads are allowed only for bootstrap/deep-review modes, scoped to the project unless I approve a global full-archive pass. Escalate only for broad/conflicting changes, low confidence, evidence-backed stale checkpoints, remote commits ahead, or major metadata changes.
17. Preserve stable task ids, review notes, and previous conclusions unless new evidence changes them. Use cheaper model tiers for classification/summarization and stronger tiers only for deep project review or design-system extraction.
18. Respect requires_approval, possible_secret, preprocessed_ref, needs_deep_review, needs_deep_design_review, repo_may_be_stale, and sync_uncertain exactly as described in docs/generative-layer.md.
19. For bootstrap or deep-review runs, checkpoint continuously. Do not keep generated output only in memory until the end. After each conversation summary, atomically merge backup_dir/_conversation_summaries.json using a temporary file and rename when possible. After each project review, atomically merge backup_dir/_project_reviews.json. If usage/time/context/provider limits stop the run, update backup_dir/_review_update_log.json with status needs_attention, pending counts, and enough checkpoint metadata to resume. Next run must resume from matching content_hash checkpoints and skip already summarized conversations.
20. Write generated sidecars only at the root of backup_dir:
   - _conversation_summaries.json
   - _project_reviews.json
   - _agent_profile.json
   - _review_repo_sync.json
   - _review_update_log.json
21. After writing sidecars, run: <review_gate_cmd> finalize --backup-dir <backup_dir> --model-provider <provider_or_agent> --model-routing <available_or_unavailable> --model-used <concrete_model_or_alias_or_unknown>
22. If the finalizer fails, do not mark the review run ok. If it records needs_attention, treat the run as completed with warnings and surface those warnings. Use _review_generated_eval_report.json and _review_update_log.json as the evidence.
23. Do not write generated sidecars into project repos, source-tool raw folders, markdown-* folders, or the trailkeep repo.
24. Never transmit the entire backup folder as an archive or unscoped dump. Use the _review_run_plan.json input manifest first.
25. Do not commit private backups or generated sidecars.

After setup, report:
- skill install path or fallback;
- automation schedule/trigger, including derived backup time and review offset if time-based;
- backup_dir;
- model tier routing availability and concrete model used or model alias;
- repo sync behavior and any stale/uncertain repos;
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
- Resolve review_gate_cmd as <trailkeep_repo>/scripts/run-project-review-agent-gates.sh. Use this wrapper for all gates. If skill_dir is outside the repo, pass --skill-dir <skill_dir> to the wrapper.
- Before any model call, run <review_gate_cmd> pre --backup-dir <backup_dir>. It also confirms the plan/eval are current and aligned, and backup_dir/log.json has a latest backup run less than 24 hours old. Continue only if it exits 0; exit 0 may be partial, so use only _review_effective_plan.json.
- If the wrapper pre command exits 0 with partial=true or pending_projects, continue only with the safe effective plan and surface the pending approval batch; do not send skipped projects or inputs to the model.
- If the wrapper pre command exits 2, resolve approval through _review_gate_decisions.json, rerun <review_gate_cmd> pre --backup-dir <backup_dir>, and then use _review_effective_plan.json for model context.
- Before model calls for a project with a local git repo, run <review_gate_cmd> repo-sync --backup-dir <backup_dir>. It may run git fetch to update remote-tracking refs, but must never pull or modify worktrees. If _review_repo_sync.json marks repo_may_be_stale or sync_uncertain, reflect that in the project review.
- Write generated sidecars only at the root of backup_dir, especially backup_dir/_project_reviews.json.
- After writing sidecars, run <review_gate_cmd> finalize --backup-dir <backup_dir>.
- If the finalizer fails, do not mark the review run ok. If it records needs_attention, treat the run as completed with warnings.
- Do not write generated sidecars into project repos, source-tool raw folders, markdown-* folders, or the trailkeep repo.
- First inspect the local repo if it exists.
- If ROADMAP.md, BACKLOG.md, TODO.md, docs/product-progress.md, docs/project-progress.md, docs/agent-handoff.md, docs/design-patterns.md, docs/design.md, design.md, AGENTS.md with continuity/product instructions, local issues/configs, or equivalents exist, treat those files as the source of truth.
- For next step, roadmap, and tasks, roadmap/backlog/product-progress win. For design-system extraction, design docs and real component files win. Conversations only explain recent decisions or undocumented changes.
- Preserve the user's existing priority/order from roadmap/backlog files. Suggested next steps should advance the existing roadmap when present.
- If conversations reveal new legitimate work not present in the roadmap, add it as a pending/candidate task or open question with evidence. Do not silently promote it above the existing roadmap priorities.
- If roadmap/backlog/todo/design docs are stale, duplicated, or contradictory, add focused recommendations to recommended_repo_doc_updates with file, reason, action, confidence, and requires_user_approval=true. Never modify repo planning docs automatically during recurring runs.
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

Use this shape when `<review_gate_cmd> pre` exits `2`, or as a non-blocking
intervention when it exits `0` with `partial: true`. Do not show raw
conversation text, suspected secret values, or unscoped backup contents.

```text
Trailkeep needs your approval for some review inputs.

I have not sent the inputs below to a model. Safe projects may continue from
_review_effective_plan.json.

Reason:
- requires_approval was set in _review_run_plan.json.

possible_secret inputs with preprocessed_ref are redacted locally and should not
appear in this approval batch. If the gate excluded a possible-secret input
because no redacted replacement existed, report it as needs_attention instead of
asking for approval by default.

Flagged inputs:
<sanitized_input_ids_from_pre_model_gate>

Choose one:
- approve this run as planned;
- exclude specific input ids and rerun the gate;
- stop this review run.

After you choose, I will write `_review_gate_decisions.json` for the current plan and rerun the gate. I will continue only after the gate exits 0 and will use `_review_effective_plan.json` for model context.
```
