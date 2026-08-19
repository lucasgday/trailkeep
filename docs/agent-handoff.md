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
  backup reprocesses existing raw rollouts once.
- Claude project attribution uses each session's authoritative `cwd`, not the
  ambiguously hyphen-encoded source-folder name. This keeps names such as
  `facturante-conversion` intact in Markdown and the Evidence Ledger; Cowork
  still folds into its intentional virtual `cowork` project.
- Claude slash-command sessions such as `/config` are skipped or marked
  `internal: true | internal_kind: local_command`. Recognition covers both the
  tag-wrapped form and the interactive `config` + `AskUserQuestion` form.
  When generated command wrappers appear inside a real conversation, the
  Markdown remains cumulative and untouched while the viewer, Ledger, review
  planner, and generated-review eval corpus remove those turns in memory. The
  planner writes a `preprocessed_ref` for affected conversations so the optional
  review runtime cannot fall back to reading the noisy raw Markdown.
  Claude v3 Markdown records
  `lineage_id`, `message_count`, and `updated_at`; the viewer, Ledger, review
  planner, and generated-review eval corpus canonicalize by either exact session
  id or shared lineage. Historical and resumed branches remain on disk.
- Claude incremental state is versioned as `claude-visible-activity-v5`, so the
  next backup refreshes `updated_at` from the last non-internal visible event.
  Ledger cache version 10 rescans current raw/Markdown with provider-normalized
  token accounting while preserving metrics carried from pruned raw. Claude
  usage is deduplicated per API response, Codex `output_tokens` is treated as
  reasoning-inclusive, and incompatible historical token measurements remain
  in `legacy_tokens` instead of affecting cross-provider rankings.
- Adjacent tool calls and results render as one flat execution with an internal
  result divider. Their legacy per-turn progress keys are preserved.
- Conversation actions include a bilingual Hide/Show Tools control. It reuses
  the existing type filter, stays synchronized with the sticky tool count,
  preserves visibility state while navigating, and keeps a 44px mobile target.
- Conversation-to-conversation navigation follows the newest-first project list
  explicitly: `↑ Newer / Más reciente` and `↓ Older / Más antigua`. The labels
  and icons describe list direction instead of previous/next chronology.
- Project Home keeps Back, Hide/archive, and Copy context in a sticky toolbar;
  Copy context is enabled and exports the existing deterministic project brief.
  Analytics and Runs use the same sticky view-header pattern. Conversation
  detail adds a bilingual reduced-motion-aware jump to the last visible turn,
  with a 44px icon target on narrow screens.
- Valid GFM Markdown tables render semantically inside turns. Empty headers are
  omitted, inline formatting is preserved, and narrow screens use a
  keyboard-focusable local scroll region instead of widening the page.
- Project cards derive their latest activity from the complete canonical
  conversation tree (`date`, `updated_at`, and completed subagents) together
  with raw project metadata. They compare full timestamps, display localized
  date and time, and therefore sort same-day activity by its actual hour.
  Claude project metadata now uses the final non-internal conversation event
  rather than the first raw line or later local-command noise.
- Project metadata also extracts explicit production deploy URLs from Claude,
  Codex, and OpenCode conversation/tool evidence on each backup run. The newest
  production mention wins over static local hints; preview, staging, and
  development URLs are excluded. Cowork remains a virtual project without
  filesystem or deploy facts.
- The local real-backup migration completed successfully: 409 internal rollouts
  were ignored and 405 existing Markdown files were explicitly marked.
- The local Claude v5 activity/internal-session migration completed successfully on
  2026-07-31: three config sessions were ignored and all five cumulative
  Markdown copies carry explicit internal markers.
  `facturante-conversion` has 44 canonical conversations; the 43 legacy
  `conversion` Markdown files remain preserved but produce no canonical ghost
  project. The Claude Ledger has 190 canonical root sessions in total after the
  cache-v10 rescan excluded remaining command-only traffic from metrics.

## Verification

- Shell syntax, converter/skill Python compilation, viewer JavaScript parsing,
  prompt drift, and automation guardrails pass.
- Backup retry, Codex subagent/internal-session, and all 24 generated-review eval
  fixture suites pass. The Codex fixture also covers stale index timestamps.
- `scripts/test-claude-project-names.cjs` covers hyphenated Claude project names
  across Markdown and Ledger attribution, the final visible activity timestamp,
  exclusion of later local-command noise, plus Cowork's virtual grouping.
- `scripts/test-claude-continuity.cjs` covers command-only and embedded-turn filtering, cumulative
  internal marking, both config storage forms, resumed lineage selection,
  same-title independent sessions, raw-pruned legacy aliases, review-plan
  selection, and tool/result grouping.
- `scripts/test-viewer-markdown.cjs` covers table recognition, empty and named
  headers, alignment, escaped/code pipes, HTML escaping, and viewer/demo parity.
- `scripts/test-ledger-token-accounting.cjs` covers repeated Claude usage rows,
  Codex reasoning-inclusive output, cache-version migration, preservation and
  exclusion of incompatible legacy measurements, plus viewer/demo aggregation parity.
- `scripts/test-project-deploy-url.cjs` covers newest-production selection,
  Claude tool results, Codex tool output, and preview exclusion from both raw
  conversations and local README hints.
- Browser QA passes for `viewer.html` and `docs/index.html`: no console errors,
  no attempted network requests, full and embedded internal command traffic
  hidden, resumed lineage reduced to one row, tool/result grouped, tool
  visibility toggled by keyboard, subagent hierarchy preserved, and mobile
  layout remains within the viewport.
  Project-card QA also covers stale raw metadata and two projects with activity
  on the same day but at different hours.
  Sticky-navigation QA scrolls Project Home and Analytics, verifies both
  toolbars stay at the container top, exercises Copy context, and checks the
  last-turn jump plus its mobile target and bilingual label.
  Markdown table QA also passes at 390px: the page remains 390px wide while the
  table scroll region contains its 420px minimum width.
- Real-backup Analytics QA passes with zero console errors or network requests:
  1,038 normalized runs are comparable and 132 legacy Claude runs are visibly
  excluded while their token evidence remains preserved. Navigation QA covers
  the explicit newer/older labels, vertical icons, destinations, and edge states.

## Remaining QA

- Fully reload the local viewer, refresh its approved folder, and confirm the
  noisy approval-review rows are gone. An already-open file page retains its
  previously loaded JavaScript until reload.
- Open “Realizar fixes de novedades del backlog” and confirm `/terminal-setup`,
  `/model`, local-command caveats, and ANSI-heavy command output are absent while
  the real conversation remains available.
- After refreshing the approved backup folder, confirm the Projects view shows
  `facturante-conversion` with 44 conversations, no canonical `conversion`
  project, no `/config` row, and one “Notas de crédito…” conversation. Confirm
  its card shows “Última conversación” with date and time and that “Recientes”
  respects the time when multiple projects changed on the same day.
- Spot-check a tool-heavy conversation and confirm each result is inside its
  corresponding tool execution rather than appearing as a separate turn; use
  “Ocultar herramientas” and confirm only user/agent turns remain.
- Open a conversation with a GFM table and confirm rows remain readable and the
  table, rather than the whole page, scrolls on a narrow viewport.
- Scroll a long Project Home and Analytics view and confirm their navigation
  bars remain reachable; in a long conversation, use “Ir al último turno” and
  confirm it lands on the final visible turn.
- In a project's oldest and newest conversations, confirm `↑ Más reciente` and
  `↓ Más antigua` match the list direction and disable at the correct edge.
- In Analytics, confirm processed tokens are labeled as fresh input + output +
  cached input, and that the legacy-coverage note remains visible until the
  missing Claude raw transcripts are recovered.
- Existing guardian `.md` files should not be deleted; cumulative preservation
  remains intentional.
- Run `node scripts/test-project-deploy-url.cjs` after future changes to project
  metadata or raw conversation parsing.
