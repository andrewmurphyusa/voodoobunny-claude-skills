<required_reading>
- `../references/pricing.md` — per-model USD/MTok rates and cache-multiplier math. Every "$X saved" estimate in this workflow's output must trace back to this table (or a `--pricing-file` override), never a guessed number.
- `../references/analysis-rubrics.md` — safe-cut vs load-bearing test and evidence requirements. This workflow produces nothing but recommendations, so this rubric is the core of the output quality.
</required_reading>

<process>
This workflow answers exactly one question: **where could token usage have been reduced without reducing quality?** It does not touch usage-habit or cost-attribution territory — stay focused on mechanics of token spend within sessions.

1. **Run the scan.** `python scripts/parse_sessions.py scan` (pass `--project`/`--since`/`--top` if the user scoped the request; `--wiki-dir`/`--no-wiki` per the user's wiki preference — the configured sessions wiki is used automatically when present). Read the resulting `summary.md` for the aggregate view: flagged sessions, aggregate waste, top sessions by cost, and the wiki/JSONL provenance split.

2. **Select sessions to inspect closely.** Prioritize sessions flagged `GAP_REWRITES`, `REPEAT_READS`, `LARGE_TOOL_RESULTS`, `LONG_CONTEXT`, or `MANY_TURNS`, plus the top few by estimated cost if not already flagged. For `"source": "wiki"` records, read the wiki page (`wiki_page` in the record) first and fall back to `extract` only when the page lacks the request-level detail a focus area needs; for `"source": "jsonl"` records, run `python scripts/parse_sessions.py extract <session.jsonl>` and read the condensed transcript. (Gap-rewrite and large-tool-result checks below often need extract-level detail; Summary/Outcome/Prompts on the page usually cover the rest.)

3. **Work each focus area using the extract + metrics.json data:**
   - **Gap rewrites** — sessions/requests where `metrics.json` shows a gap-rewrite event (cache expired mid-session due to a long pause, forcing an expensive cache-write re-send). Confirm in the extract whether the gap was avoidable (idle time between unrelated turns — safe cut, e.g. "batch your questions instead of trickling them in") or necessary (waiting on genuinely long-running external work — load-bearing).
   - **Re-reads** — files read 2+ times per the script's `REPEAT_READS` accounting. Check the extract: was the re-read because content plausibly changed (load-bearing) or because the same unmodified file was re-read out of habit / lost context (safe cut — recommend caching the read, referencing line ranges already known, or restructuring the task to read once).
   - **Large tool results** — the top-5 largest tool results per session from `metrics.json`. Check whether the full result was needed or whether a narrower query (targeted `Grep`/`Read` with line ranges, a `head_limit`, a more specific glob) would have sufficed.
   - **Long-context sessions** — sessions flagged `LONG_CONTEXT` (last-request context > 150k tokens). Identify in the extract what drove the growth (large early tool results never pruned, accumulated re-reads, sprawling conversation) and whether splitting into fresh sessions/subagents at a natural checkpoint would have avoided carrying that context forward.
   - **Subagent opportunities** — turns in the extract where a large, self-contained investigation (broad search, multi-file read, research) was done inline in the main session instead of delegated to a subagent whose context wouldn't persist into the parent. Flag these as opportunities, not certainties — subagent delegation has its own overhead, so only recommend it where the inline investigation was large relative to its contribution to the final answer.

4. **Write every recommendation with:** the session id, the specific evidence (timestamp/request index + quoted or closely-paraphrased extract snippet, or the exact `metrics.json` figure), an estimated dollar impact using `references/pricing.md` math (stated as counterfactual API-equivalent, not real spend, per the flat-rate-plan framing), and an explicit **safe cut** or **load-bearing** tag with the one-sentence rationale for that tag (per `references/analysis-rubrics.md`'s test: did the spend contribute to task success?).

5. **Present findings** grouped by focus area, ordered by estimated impact within each group. If this workflow is being run standalone (not via `full-retro`), skip the report template and trend comparison — just present the findings directly in chat, with a note of which run directory (`~/.claude/session-retro/runs/<timestamp>/`) the underlying scan data lives in for reference.
</process>

<success_criteria>
- Scan was run; no aggregate numbers were hand-computed.
- All five focus areas (gap rewrites, re-reads, large tool results, long-context sessions, subagent opportunities) were considered, not just whichever was most visible in `summary.md`.
- Sessions were inspected via their wiki page or `extract`, never via a raw `.jsonl` read.
- Every recommendation cites session id + evidence and carries an explicit safe-cut/load-bearing tag with rationale.
- Every dollar figure is framed as counterfactual API-equivalent cost, sourced from `references/pricing.md` math.
- No usage-habit or cost-attribution content leaked into this workflow's output — it stays scoped to token-efficiency mechanics.
</success_criteria>
