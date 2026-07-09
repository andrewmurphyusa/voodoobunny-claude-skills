---
name: session-retro
description: Analyzes past Claude Code session transcripts for token efficiency, usage habits, and API-equivalent cost attribution. Use when asked to review or retro past Claude Code sessions, find token waste, understand how the user works with Claude Code, or estimate what a flat-rate plan's usage would have cost against API pricing.
---

<essential_principles>
**Scripts count, Fable judges.** The deterministic parser (`scripts/parse_sessions.py`) does ALL aggregation, math, and totals — token counts, cost sums, gap detection, dedup. Fable's job is qualitative judgment on top of already-computed numbers: reading condensed extracts, deciding what matters, writing recommendations. Never re-derive a total by eyeballing a transcript when the script already computed it.

**Never read raw session JSONL wholesale.** Session files are large (tens of MB across a corpus) and full of duplicate/streaming noise. Always go through `scripts/parse_sessions.py scan` (aggregate metrics) or `scripts/parse_sessions.py extract <file>` (condensed single-session transcript). Do not `cat`, `Read`, or `grep` a raw `.jsonl` session file directly.

**Don't duplicate existing tools.** ccusage already owns ground-truth cost/usage totals. `rtk gain` / `rtk discover` already own token-savings-from-RTK-usage analysis. `/fewer-permission-prompts` already owns permission-prompt reduction. `/cost` and `/usage` already own live session cost display. This skill's job is the layer those tools don't do: cause attribution (why a session was expensive), counterfactuals (what it would have cost done differently), and quality-aware judgment (safe cut vs load-bearing spend) across a corpus of past sessions. See `references/existing-tools.md` before writing any finding that smells like "total tokens used" or "total cost" — check it isn't just restating a number ccusage already reports.

**Every finding must cite session id + evidence.** No finding, recommendation, or habit observation may appear in output without a session id (filename/uuid), a timestamp or request index, and a quoted or closely-paraphrased snippet from the extract that supports it. Unsupported claims are not findings.

**Tag every recommendation safe-cut or load-bearing.** For every "you could have spent less here" recommendation, explicitly label it **safe cut** (would not have changed the outcome) or **load-bearing** (the spend contributed to the task succeeding — cutting it risks quality). See `references/analysis-rubrics.md` for the test to apply.

**The user is on a flat-rate plan.** All dollar figures this skill produces are counterfactual — "what this usage would have billed on the API" — not real spend. Every report, table, and verbal summary that shows a dollar amount must make this framing explicit (e.g. "est. API-equivalent cost" rather than "cost"). Never imply the user was charged these amounts.
</essential_principles>

<intake>
Ask the user (or infer from their request) which analysis they want:

1. **Full retro** (default) — token efficiency + usage habits + cost attribution, combined into one report with trend comparison.
2. **Token efficiency only** — find token-usage reductions that would not have reduced quality.
3. **Usage habits only** — find improvements to how the user works with Claude Code.
4. **Cost attribution only** — attribute and explain API-equivalent cost, with counterfactuals.

If the user's request doesn't clearly indicate one of these, default to option 1 (full retro).
</intake>

<routing>
| Intake choice | Workflow file |
|---|---|
| 1. Full retro (default) | `workflows/full-retro.md` |
| 2. Token efficiency only | `workflows/token-efficiency.md` |
| 3. Usage habits only | `workflows/usage-habits.md` |
| 4. Cost attribution only | `workflows/cost-attribution.md` |

Load and follow the routed workflow file's `<required_reading>` and `<process>` in full before producing output.
</routing>

<script_index>
All analyses run through `scripts/parse_sessions.py` (Python 3, stdlib only — invoke with plain `python`, no `rtk` prefix since RTK has no filter for this script's output shape):

- `python scripts/parse_sessions.py scan [--claude-dir DIR] [--project SUBSTRING ...] [--since YYYY-MM-DD] [--out DIR] [--top N] [--sonnet5-intro] [--pricing-file JSON]` — walks `~/.claude/projects/**/*.jsonl`, aggregates every session, and writes `metrics.json` + `summary.md` to `~/.claude/session-retro/runs/<YYYYMMDD-HHMMSS>/`. Run this first in every workflow.
- `python scripts/parse_sessions.py extract <session.jsonl> [--max-text N] [--max-tool N]` — prints a condensed, cheap-to-read transcript of one session to stdout. Use this instead of reading the raw session file.
</script_index>

<reference_index>
- `references/jsonl-format.md` — verified schema of Claude Code session JSONL records (record types, `message`/`usage` keys, quirks like duplicate lines and mixed cache-TTL fields).
- `references/pricing.md` — per-model USD/MTok rates and cache-multiplier math used by the parser; check its staleness note before trusting it on an old checkout.
- `references/existing-tools.md` — what ccusage, rtk gain/discover, /fewer-permission-prompts, /cost, /usage, and dashboard tools already cover, and the rule for what this skill should add instead of repeat.
- `references/analysis-rubrics.md` — the safe-cut vs load-bearing test, the habit-mining rubric, counterfactual-honesty rules, and evidence requirements. Required reading for every workflow.
</reference_index>

<workflows_index>
- `workflows/full-retro.md` — runs all three analyses across a selected sample of sessions, fills `templates/retro-report.md`, and compares against the previous run for trends.
- `workflows/token-efficiency.md` — analysis (a) only: token-usage reductions that don't cost quality (gap rewrites, re-reads, large tool results, long context, subagent opportunities).
- `workflows/usage-habits.md` — analysis (b) only: semantic patterns in how the user works with Claude Code (repeated instructions, corrections, clarification loops, abandoned work, model-mix opportunities).
- `workflows/cost-attribution.md` — analysis (c) only: attributes API-equivalent cost to causes and produces counterfactuals, cross-checked against ccusage.
</workflows_index>
