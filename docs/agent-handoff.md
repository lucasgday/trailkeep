# Agent handoff

Operational continuity for substantive trailkeep implementation and QA work.
Update this file after changes that affect backup correctness, viewer behavior,
generated-review inputs, or release verification.

## Current state

- Codex Desktop `guardian` rollouts are recognized as internal
  approval-review machinery and are not converted into conversations.
- Codex conversation activity dates come from the latest rollout event rather
  than trusting a potentially stale `session_index.jsonl` timestamp. Long-lived
  automation threads therefore remain discoverable under their real recent
  activity date.
- Cumulative guardian Markdown created by older trailkeep versions remains on
  disk. When the matching raw rollout is available, the converter adds
  `internal: true | internal_kind: approval_review`; the viewer, Evidence
  Ledger, review planner, and generated-review eval corpus exclude that explicit
  identity. A conservative content signature covers raw-pruned legacy files.
- Codex incremental state is versioned as `codex-subagents-v2`, so the next
  backup reprocesses existing raw rollouts once. Ledger cache version 6 likewise
  rescans current raw/Markdown while preserving metrics carried from pruned raw.
- The local real-backup migration completed successfully: 409 internal rollouts
  were ignored and 405 existing Markdown files were explicitly marked.

## Verification

- Shell syntax, converter/skill Python compilation, viewer JavaScript parsing,
  prompt drift, and automation guardrails pass.
- Backup retry, Codex subagent/internal-session, and all 24 generated-review eval
  fixture suites pass. The Codex fixture also covers stale index timestamps.
- Browser QA passes for `viewer.html` and `docs/index.html`: no console errors,
  no attempted network requests, legacy guardian content hidden, subagent
  hierarchy preserved, and mobile layout remains within the viewport.

## Remaining QA

- Fully reload the local viewer, refresh its approved folder, and confirm the
  noisy approval-review rows are gone. An already-open file page retains its
  previously loaded JavaScript until reload.
- Existing guardian `.md` files should not be deleted; cumulative preservation
  remains intentional.
