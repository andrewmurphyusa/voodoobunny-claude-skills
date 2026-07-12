# Tests for session-retro

Stdlib `unittest` only. No pip installs, no network, no dependency on live
`~/.claude` data — everything runs against the committed synthetic fixture that
lives in the sibling build-sessions-wiki skill
(`../../build-sessions-wiki/tests/fixtures/`).

## Run

```
python -m unittest discover -s skills/session-retro/tests -p "test_*.py"
```

## What's covered (`test_parse_sessions.py`)

Parsing itself is tested in build-sessions-wiki (`test_session_core.py`); this
suite targets the layer session-retro adds on top of the shared core:

- **Pricing** — `price_token_buckets` at known rates, unknown-model → opus
  fallback, and the Sonnet 5 intro-rate toggle.
- **`record_from_core_metrics`** — the single function both cost paths use.
  Verifies exact fixture costs (`cost_total == 1.2028`, `wasted_usd == 1.14`,
  dollar-based `GAP_REWRITES` flag), the empty and `before_since` returns, and
  `None` on malformed core metrics.
- **Wiki path + fallback** — a temp wiki page with a matching fingerprint is
  read instead of the JSONL (and prices identically); a broken metrics block
  falls back to JSONL with a warning; a page from another machine is ignored.
- **Scan aggregation** — `build_scan_metrics` totals/provenance without a wiki,
  and `render_summary` emitting the provenance + counterfactual framing.

## Dependency note

`parse_sessions.py` imports `session_core.py` from the build-sessions-wiki skill
via a `sys.path` shim, so that skill must sit beside session-retro under
`skills/`. These tests assert that coupling works.
