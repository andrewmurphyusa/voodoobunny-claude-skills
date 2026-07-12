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

- `test_session_core.py` — the shared parser (`scripts/session_core.py`).
  Covers the primitives (`resolve_model_key`, `usage_token_buckets`,
  `dedupe_assistant_records`), the pure sub-analyses (`detect_gap_events`,
  `compute_flags`, `count_user_prompts`, `context_growth`), and
  `metrics_from_records` driven by tiny **in-memory** record lists — one focused
  case per parsing rule, no fixture files needed — plus `render_extract` /
  `collect_prompts_from_records`.
- `test_wiki_tools.py` — wiki-specific helpers in `wiki_tools.py`
  (`coerce_config_value`, `config_set`, `compute_staleness`, `resolve_from_time`,
  `classify_session_status`, `build_plan`, `order_pages`/`render_index`/
  `build_tag_map`/`render_tags`) plus `compute_session_metrics` on the committed
  fixture (integration).
- `test_contract.py` — cross-skill guard. Confirms session-retro's
  `parse_sessions.py` imports this very `session_core` module (not a copy), and
  that the JSONL and wiki cost paths converge on an identical priced record for
  the fixture. Run after touching `session_core.py` or either command script.

session-retro's pricing + scan layer is tested separately in
`skills/session-retro/tests/`.

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
