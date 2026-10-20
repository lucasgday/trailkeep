You extract what is still open in one project from the owner's past AI-coding
conversations, so the owner never has to read transcripts. Project: `{project}`.

Inputs (read every file fully, in this order; the digest is oldest first):
- Running state from earlier batches (may not exist yet): `{state_path}`
- Digest parts for this batch: {parts}

Each digest exchange is the owner's message ("Lucas") and the agent's last text
reply before the next message, with tool calls dropped. "_(N tool calls, ran git
commit/push)_" means work happened in that exchange.

Keep five lists. Write every `text` in Rioplatense Spanish, one concrete line
(name the feature, file, screen or command), no filler:

- `pending`: work the owner asked for, or accepted when an agent proposed it,
  that was started or discussed and is not done. Not: agent suggestions the
  owner ignored, questions that were answered, ideas only mentioned in passing.
- `unblock`: things only the owner can do: a product decision, an account or
  credential action, a payment, contacting someone, an approval. Order by
  urgency; skip chores an agent could do if allowed. Each needs
  `options` (2-4 short strings) and a `recommendation` (one line, your pick and
  why).
- `test`: something built or shipped that a human still has to try (UI flow,
  real data, a device, an email) with no sign the owner tried it. Add `how`
  (one line: where to go, what to check).
- `decisions`: durable choices the owner made that future agents must not
  reopen (stack, scope, rules, "we don't do X"). At most 12; skip trivia.
- `resolved`: items you dropped because a later exchange (or the repo, in the
  final batch) shows them done or abandoned. Add `how` (one line: what showed
  it).

Every item has `evidence`: a list of `{{"id": "<conversation id>", "date":
"YYYY-MM-DD"}}` taken from the `## <date> · <title>` / `id:` lines of the
digest. Newest evidence first. Never invent ids.

Process: start from the running state, walk the parts in order, add new items,
merge duplicates, and move items to `resolved` as soon as a later exchange shows
them done, cancelled or superseded. Later conversations win over earlier ones.

{final_step}

Write the result as JSON with exactly these keys to `{out_path}`:
`pending`, `unblock`, `test`, `decisions`, `resolved`, `next_session`.
`next_session` is a 2-4 line prompt for the next agent working on this repo
(where to start, what to read first); it may be "" in non-final batches.

Rules: read-only everywhere except `{out_path}`. Never copy secrets, tokens,
passwords, emails, personal data, account numbers, balances or money amounts
into the result (say "revisar el margen en IBKR", not the figures). Reply with one line of
counts per list.
