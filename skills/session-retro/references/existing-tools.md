# What this skill must not duplicate

There is a hard constraint on this skill: **do not re-derive analysis that popular existing tools already do well.** This skill's value-add is cause attribution, counterfactuals, and qualitative judgment — not counting.

## Tools already covering this space

- **ccusage** (`npx ccusage`) — the ground-truth tool for token/cost totals: overall spend, 5-hour billing blocks, per-model breakdowns. If a number ccusage already reports is needed (e.g. "total tokens this month"), **cite ccusage's output**, don't recompute it independently in a way that could disagree.
- **`rtk gain` / `rtk gain --history`** — RTK's own token-savings accounting for commands run through the `rtk` wrapper. This skill does not analyze RTK's savings; that's a separate concern (tool-call filtering, not session/model spend).
- **`rtk discover`** — analyzes Claude Code sessions for *missed RTK usage* (commands that should have been prefixed with `rtk` but weren't). This skill does not hunt for missed-rtk-prefix opportunities — that's `rtk discover`'s job.
- **`/fewer-permission-prompts`** — scans transcripts for common read-only Bash/MCP calls and proposes an allowlist. This skill does not produce permission-allowlist recommendations — that's this command's job.
- **`/cost` and `/usage`** (Claude Code built-ins) — session/window-level cost and usage display. This skill does not replace the at-a-glance built-in displays.
- **sniffly** and **claude-code-templates dashboards** — third-party visualization/dashboard tools over Claude Code session data (charts, live dashboards). This skill does not produce a dashboard or visualization layer; its output is a written report.

## The rule

1. **Cite ccusage as ground truth for totals.** When the report states an aggregate dollar or token figure that ccusage can also produce, cross-check against ccusage's output and note it (see the cost-attribution workflow's "ccusage cross-check" section of the report template). If this skill's independently-computed total materially disagrees with ccusage, say so explicitly rather than silently picking one number.
2. **This skill adds exactly three things existing tools don't:**
   - **Attribution** — *why* a session cost what it did (gap-rewrites, re-reads, oversized tool results, long-context drift), not just *how much*.
   - **Counterfactuals** — what it would have cost done differently (e.g. "compacting at turn 40 would have saved ~$X", "this turn was Haiku-eligible and would have cost $Y less").
   - **Qualitative judgment** — safe-cut vs load-bearing spend, habit-mining across sessions, corrections/re-asks that suggest a CLAUDE.md or skill gap. These require reading transcript content, which none of the counting tools do.
3. When in doubt about whether a proposed finding duplicates an existing tool, ask: "could `ccusage`, `rtk gain`, `rtk discover`, or `/fewer-permission-prompts` already answer this without reading any transcript text?" If yes, drop it or defer to that tool by name instead of restating its output.
