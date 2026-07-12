# Tests for the sessions-wiki skill family

Stdlib `unittest` only — no pip installs, no network, no dependency on the
user's live `~/.claude` data. Everything runs against the committed synthetic
fixture under `fixtures/`.

## Run

From the repo root (or anywhere):

```
python -m unittest discover -s skills/build-sessions-wiki/tests -p "test_*.py"
```

Or from this directory: `python -m unittest`.

## What's covered

- `test_wiki_tools.py` — unit tests for `wiki_tools.py`. Targets the pure /
  compute-only functions the refactor exposed (`resolve_model_key`,
  `usage_token_buckets`, `dedupe_assistant_records`, `coerce_config_value`,
  `classify_session_status`, `compute_staleness`, `resolve_from_time`,
  `compute_session_metrics`, `build_plan`, `render_index`/`render_tags`,
  `config_set`) so tests assert on returned data instead of parsing stdout.
- `test_contract.py` — cross-script contract test. Feeds the same fixture
  through `wiki_tools.compute_session_metrics` and session-retro's
  `parse_sessions.process_session_file` and asserts they agree on token buckets,
  counts, per-model sums, the source fingerprint, and model-key resolution.
  **This is the guard against the two skills' duplicated parsing logic drifting.**

## The fixture (`fixtures/projects/c--fixture-proj/`)

`11111111-…-111111111111.jsonl` is a hand-built session exercising every parsing
rule that has bitten us, with known expected numbers (see assertions):

| Rule | How the fixture triggers it | Expected |
|---|---|---|
| dedup by (id, requestId), keep last | assistant `m1/r1` appears twice, outputs 999 then 10 | output counts 10, not 999 |
| `<synthetic>` skipped | one `model:"<synthetic>"` record | not counted |
| malformed line tolerated | one deliberately broken line | `warnings_count >= 1` |
| subagent (sidechain) attribution | `…/111…/subagents/agent-aaaa.jsonl` | `sidechain_requests == 1` |
| human-prompt counting | 1 real prompt + a tool_result turn + an `isMeta` turn + a sidechain task prompt | `user_prompts == 1` |
| TTL-aware gap rewrite | 2h gap before a 60k-token 1h cache write | 1 gap event, `GAP_REWRITES` flag |
| repeat reads | `a.txt` read in two turns | `repeat_reads == {"a.txt": 2}` |
| ai-title / summary capture | one of each record type | surfaced in metrics |

`22222222-…-222222222222.jsonl` is an aborted session (no assistant turn) →
`compute_session_metrics` returns `{"empty": True}`.

If you change a threshold or parsing rule in `wiki_tools.py`, update the fixture
and the expected numbers together.
