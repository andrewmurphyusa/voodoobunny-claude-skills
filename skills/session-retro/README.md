# session-retro

Analyzes your past Claude Code session transcripts for token efficiency, usage habits, and API-equivalent cost attribution — then hands you a report with cited, actionable findings instead of just totals.

## What it does

Most usage-tracking tools (ccusage, `rtk gain`, `/cost`, `/usage`) tell you *how much* you used. This skill answers the questions those tools don't:

- **Token efficiency** — which sessions wasted tokens on avoidable cache rewrites, redundant file re-reads, oversized tool results, or runaway context growth — and which of those were actually necessary for the work to succeed.
- **Usage habits** — patterns in how you work with Claude Code: instructions you keep repeating (candidates for `CLAUDE.md` or a new skill), corrections after ambiguous prompts, clarification round-trips that could have been front-loaded, abandoned or restarted work, and places you may be over- or under-paying for model capability.
- **Cost attribution** — where API-equivalent cost actually went (cache-rewrite waste, re-reads, context overhead, the rest), plus counterfactuals ("restarting at request #40 would have saved an estimated $X–$Y") and a rough cost-per-completed-task figure.

## Important: this is counterfactual cost, not a bill

**If you're on a flat-rate Claude plan, every dollar figure this skill produces is hypothetical** — "what this usage would have cost if billed at API rates," not money you were actually charged. The skill exists to help you reason about efficiency and habits using a familiar unit (dollars), not to report real spend. Every report states this framing explicitly.

## Install

```
/plugin install session-retro@voodoobunny-claude-skills
```

## Usage

Invoke the skill and it will ask which analysis you want (or infer it from your request):

```
Run a session retro on my last month of Claude Code usage
```

```
Find token waste in my Daily repo sessions
```

```
How could I be working better with Claude Code?
```

```
What would my usage this week have cost on the API?
```

These map to the skill's four modes: **full retro** (default — all three analyses combined, with trend comparison to your last run), **token efficiency only**, **usage habits only**, and **cost attribution only**.

## How it works

The design principle is **"scripts count, Fable judges."**

1. A deterministic Python parser (`scripts/parse_sessions.py`) walks your local `~/.claude/projects/**/*.jsonl` session files, dedupes duplicate streamed records, and computes all the aggregation: token totals, per-session cost, cache-rewrite waste, repeated file reads, oversized tool results, context growth, and flags for sessions worth a closer look. This is where every number in the eventual report comes from — Claude never eyeballs a total.
2. Claude reads only the parser's condensed output: a corpus-level `summary.md` and, for a small selected sample of sessions (the most expensive, the flagged ones, plus a couple of random ones as a baseline), a per-session condensed extract — never the raw JSONL.
3. Claude applies judgment on top of those numbers: which spend was load-bearing vs a safe cut, which habits are worth changing, what a plausible counterfactual would have cost — always citing the specific session and evidence behind each claim.

This split keeps the analysis cheap (Claude never reads megabytes of raw transcript) and keeps the numbers trustworthy (they come from code, not a language model estimating token counts).

## Output location

Each run writes to a timestamped directory:

```
~/.claude/session-retro/runs/<YYYYMMDD-HHMMSS>/
  metrics.json     # full aggregate data from the parser
  summary.md       # human-readable aggregate summary
  report.md        # (full-retro only) the filled analysis report
```

Keeping these around lets each new full retro compare itself against the previous run and call out trends (recurring flags, whether past recommendations were acted on).

## Privacy

All parsing and analysis runs locally against files already on your machine (`~/.claude/projects/`). Session transcripts are never uploaded, sent to a third-party service, or included verbatim in this skill's own repo — only the run outputs under `~/.claude/session-retro/runs/` are written, and those stay on your machine like the source transcripts they summarize.

## Extending

- **Tune flag thresholds:** the parser's gap-rewrite/re-read/large-tool-result/long-context/many-turns thresholds are starting points (see the parser's own comments); adjust them if your usage pattern trips too many or too few flags.
- **Add a pricing override:** pass `--pricing-file <path.json>` to `scan` if you need rates that differ from `references/pricing.md` (new models, negotiated rates, etc).
- **Add a new focus area:** each analysis lives in its own workflow file under `workflows/`; add a new one and route to it from `SKILL.md`'s intake/routing tables rather than overloading an existing workflow.
- **Update pricing:** `references/pricing.md` is dated at authoring time — if it's more than about a month old, re-verify current rates before trusting cost output.
