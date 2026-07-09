# Pricing reference

> **Cached 2026-07-07.** If it is more than a month stale when you read this, verify current pricing via the `claude-api` skill before computing any costs. Do not compute costs off stale numbers without checking.

## Rates (USD per million tokens, input / output)

| Model family | Input | Output |
|---|---|---|
| Fable 5 / Mythos 5 | $10 | $50 |
| Opus 4.8 / 4.7 / 4.6 | $5 | $25 |
| Sonnet 5 (standard) | $3 | $15 |
| Sonnet 5 (intro pricing, through 2026-08-31) | $2 | $10 |
| Sonnet 4.6 | $3 | $15 |
| Haiku 4.5 | $1 | $5 |

**Sonnet 5 intro pricing note:** Sonnet 5 is discounted to $2/$10 per MTok through 2026-08-31, reverting to the standard $3/$15 after that date. The parser's `--sonnet5-intro` flag selects the intro rate explicitly; when analyzing historical sessions, use whichever rate was actually in effect on that session's date, and when reporting, show both intro and standard Sonnet 5 figures side by side so the reader can see the difference (per `cost-attribution` workflow).

## Cache math

- **Cache read**: ≈ **0.1×** the model's input rate.
- **Cache write, 5-minute TTL**: ≈ **1.25×** the model's input rate.
- **Cache write, 1-hour TTL**: ≈ **2.0×** the model's input rate.

Claude Code predominantly writes 1-hour TTL cache entries (see `jsonl-format.md`) — do not assume 5-minute-only caching when estimating cache-write cost or gap-rewrite waste.

### Gap-rewrite wasted-cost formula

For a request that had to pay a fresh cache-write premium instead of a cheap cache-read (a "gap rewrite" — see `analysis-rubrics.md` and the parser's `scan` output), the wasted dollars for that event are approximately:

```
wasted_usd = (w5m * (1.25 - 0.1) + w1h * (2.0 - 0.1)) * input_rate / 1_000_000
```

where `w5m` / `w1h` are the 5-minute / 1-hour cache-write token counts for that request and `input_rate` is the model's per-MTok input rate.

## `--pricing-file` override shape

The parser accepts `--pricing-file <path.json>` to override built-in rates without editing code. The shape is a flat JSON object keyed by the parser's pricing keys — exactly `fable`, `opus`, `sonnet5`, `sonnet5_intro`, `haiku` (these are the resolved keys, not raw model strings; `mythos` maps to `fable`, all Sonnet models map to `sonnet5`):

```json
{
  "sonnet5": { "input": 3, "output": 15 },
  "sonnet5_intro": { "input": 2, "output": 10 },
  "fable": { "input": 10, "output": 50 }
}
```

- Only include the keys you want to change; the parser merges each entry over its built-in default. Partial entries (e.g. only `"input"`) also merge.
- `input` / `output` are USD per million tokens.
- Cache multipliers (0.1× read, 1.25× 5m write, 2.0× 1h write) are constants in the script and are **not** overridable via the pricing file — edit `scripts/parse_sessions.py` if they ever change.
- The script itself is the source of truth: see `DEFAULT_PRICING` and `load_pricing()` at the top of `scripts/parse_sessions.py`.
