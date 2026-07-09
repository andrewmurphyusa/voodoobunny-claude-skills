# Claude Code session JSONL format (verified)

Facts below were empirically checked against real session files on 2026-07-07. Do not invent additional fields — if you need something not listed here, re-inspect real data rather than guessing.

## File locations

- `~/.claude/projects/<munged-project-dir>/<uuid>.jsonl` — one file per session.
- Windows: `~` resolves to `C:\Users\voodo`, i.e. `C:\Users\voodo\.claude\projects\`.
- Project directory names are the project path with path separators munged (e.g. `c--sourcecode-github-Daily`).
- Corpus observed at cache time: ~37 MB total, 5 project dirs, 20 sessions under `c--sourcecode-github-Daily`.
- Largest sampled file: `~/.claude/projects/c--sourcecode-github-Daily/5f1aaaac-0bdd-4b9d-9f48-2cd230909ad2.jsonl`.

### Subagent (sidechain) transcripts live in separate nested files

**Verified 2026-07-07 against real data.** Subagent (Task-tool) transcripts are stored in `<project-dir>/<session-id>/subagents/agent-*.jsonl` — *not* inline in the parent session's `.jsonl` as `isSidechain: true` records. A non-recursive glob over `*.jsonl` at the project-dir level silently misses them; in the verified corpus that dropped ~870 requests and ~14% of total cost, and made sidechain cost always read $0. The parser (`find_subagent_files()` in `scripts/parse_sessions.py`) pulls these in and attributes them to the parent session's sidechain totals — any reimplementation must do the same.

### Offloaded tool results (rare)

Some sessions offload very large tool results to `<project-dir>/<session-id>/tool-results/*.txt` files referenced from the JSONL instead of inlining the content. Observed in 1 session of the verified corpus. The parser does not follow these references, so `large_tool_results` may slightly undercount for such sessions — a known, accepted limitation, not a bug.

## Record types

Each line is one JSON object. `type` values observed in sampled data:

- `assistant`
- `user`
- `queue-operation`
- `ai-title`
- `file-history-snapshot`
- `last-prompt`

Also expected (not sampled, but present in other files per Claude Code conventions): `summary`, `system`.

## Assistant records

Top-level keys: `cwd, entrypoint, gitBranch, isSidechain, message, parentUuid, requestId, sessionId, timestamp, type, userType, uuid, version`.

`message` keys: `content, diagnostics, id, model, role, stop_details, stop_reason, stop_sequence, type, usage`.

### `usage` field structure

```
usage: {
  input_tokens,
  cache_creation_input_tokens,
  cache_read_input_tokens,
  output_tokens,
  server_tool_use: { web_search_requests, web_fetch_requests },
  service_tier,
  cache_creation: {
    ephemeral_5m_input_tokens,
    ephemeral_1h_input_tokens
  },
  inference_geo,
  iterations: [...],
  speed
}
```

- `cache_creation_input_tokens` is the total cache-write tokens; `cache_creation.ephemeral_5m_input_tokens` / `.ephemeral_1h_input_tokens` is the breakdown by TTL. These two should sum to (approximately) `cache_creation_input_tokens`.
- **Claude Code predominantly uses the 1-hour cache TTL** — sampled data showed `ephemeral_1h_input_tokens` dominating over 5m tokens. Any gap-rewrite or cache-waste analysis must be TTL-aware: use a 3600s gap threshold when 1h tokens dominate for a session, 300s when 5m tokens dominate. Do not assume 5-minute-only caching.

### Duplicate-line dedupe rule

Duplicate assistant lines exist for the same underlying API response (identical `usage` values appear twice in the raw file, most likely from streaming/retry artifacts in how Claude Code writes the transcript). This roughly **doubles apparent cost** if not handled.

**Rule: dedupe by `(message.id, requestId)`, keep the last occurrence.**

### Model values and resolution rule

`model` values observed in one sampled file (with counts): `"claude-sonnet-5"` (131), `"sonnet"` (8), `"haiku"` (8), `"<synthetic>"` (1).

- `<synthetic>` records carry no real cost — **skip them** entirely (no tokens billed).
- Resolve any other model string by **substring match**, case-insensitive:
  - contains `fable` or `mythos` → Fable/Mythos rates
  - contains `opus` → Opus rates
  - contains `sonnet` → Sonnet 5 rates
  - contains `haiku` → Haiku rates
  - no match → fall back to Opus rates (most conservative/expensive) **and flag the record** so the discrepancy is visible in output, rather than silently mis-costing it.

## User records

Top-level keys include the same envelope as assistant records, plus:

- `toolUseResult` — top-level field on user records that carry a tool result.
- Content may include `tool_result` blocks (the actual tool output payload).
- `isMeta` — may be present and `true` to mark non-prompt user records (e.g. system-injected messages, not real user turns). Exclude `isMeta` records when counting user prompts.
- `isSidechain` — present on both user and assistant records. Main-session files show `isSidechain: false`; subagent turns live in the separate nested `subagents/agent-*.jsonl` files (see File locations above) and should be tallied and costed as sidechain activity attributed to the parent session, not merged into the main thread silently. A subagent's synthesized task prompt is not a human prompt — exclude sidechain records from user-prompt counts.

## User prompt counting

Count a user record as a "prompt" only if: `isMeta` is not `true`, AND the content is either a plain string or a list of text blocks that does **not** consist solely of a `tool_result` block. (A record that's purely a tool result being fed back to the model is not a new user prompt.)

## Timestamps

Parse with `datetime.fromisoformat(ts.replace('Z', '+00:00'))`. Guard every `json.loads` call with try/except — malformed or partial lines exist in the wild (e.g. from an interrupted write) and must not crash the parser.
