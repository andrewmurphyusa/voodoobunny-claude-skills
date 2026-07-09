<required_reading>
- `../references/analysis-rubrics.md` — safe-cut vs load-bearing test, habit-mining rubric, counterfactual-honesty rules, evidence requirements. Apply this to every finding across all three analyses.
- `../references/pricing.md` — pricing table and cache-multiplier math backing every dollar figure in the report. Confirm it isn't stale before quoting it.
- `../references/existing-tools.md` — what ccusage/rtk/fewer-permission-prompts already cover. Do not restate their numbers as findings.
- `../references/jsonl-format.md` — schema reference for interpreting `extract` output correctly (record types, usage fields, cache TTL fields, dedup quirks).
- `../templates/retro-report.md` — the report template to fill and write out.
</required_reading>

<process>
1. **Run the scan.** `python scripts/parse_sessions.py scan` (add `--claude-dir`, `--project`, `--since`, `--top`, `--sonnet5-intro`, or `--pricing-file` if the user specified scope or pricing constraints). This writes `metrics.json` and `summary.md` to a new `~/.claude/session-retro/runs/<YYYYMMDD-HHMMSS>/` directory. Note this run directory path — the report gets written there.

2. **Read `summary.md`.** This is the aggregate view: overall totals, per-project table, top-10 sessions by cost with flags, aggregate waste, model mix, and hint lines with exact `extract` commands. Do not re-derive any of these numbers yourself — read them as given.

3. **Select the session sample.** From `metrics.json`/`summary.md`, build the sample as the union of:
   - The **top 3 sessions by estimated cost**.
   - **All flagged sessions** (any of `GAP_REWRITES`, `REPEAT_READS`, `LARGE_TOOL_RESULTS`, `LONG_CONTEXT`, `MANY_TURNS`), regardless of cost rank.
   - **2 random sessions** with at least 5 user prompts, chosen from sessions not already in the sample above (for a baseline / control against the flagged and expensive ones).

   De-duplicate the resulting list by session id. Note in the eventual report which selection reason(s) applied to each session.

4. **Extract and read each selected session.** For each session id in the sample, run `python scripts/parse_sessions.py extract <path-to-session.jsonl>` (add `--max-text`/`--max-tool` only if a session's default extract is still too large to read comfortably) and read the condensed transcript output. This is the only per-session reading step — never open the raw `.jsonl`.

5. **Apply the rubrics.** For each candidate finding surfaced while reading the extracts, run it through `references/analysis-rubrics.md`: confirm it has session id + timestamp/request index + quoted evidence, classify safe-cut vs load-bearing where applicable, and keep counterfactuals honest (state assumptions, give ranges, flag small-sample caveats — especially for the 2 random-sample sessions, which are not representative on their own).

6. **Fill the report template.** Populate `templates/retro-report.md` in full: header (run date, corpus stats, pricing basis — including the flat-rate-plan / counterfactual-cost framing), executive summary, (a) token efficiency findings table, (b) habit changes ranked top-10 with transcript citations, (c) cost attribution (category table + counterfactuals + ccusage cross-check), methodology + caveats section.

7. **Write the report into the run directory.** Save the filled template as `report.md` inside the same `~/.claude/session-retro/runs/<YYYYMMDD-HHMMSS>/` directory the scan created in step 1, alongside `metrics.json` and `summary.md`.

8. **Compare against the previous run for trends.** List the subdirectories of `~/.claude/session-retro/runs/` (excluding the one just created), take the most recent one that contains a `report.md`, and diff the two at a summary level: total estimated cost, waste categories, flag counts, and any recurring findings (same file/pattern flagged again = a habit that didn't get fixed). Add a "Trend vs previous run" section to the report with this comparison, or note "no previous run found — this is the first retro" if none exists.

9. **Present to the user.** Summarize the report's key points in the chat response (executive summary + the highest-impact 3-5 findings across all three categories + the trend note), and point to the full `report.md` path for details. Do not paste the entire report inline unless asked.
</process>

<success_criteria>
- `scan` was run and its run directory identified; no metrics were hand-computed outside the script.
- The session sample was built using exactly the specified rule (top 3 by cost + all flagged + 2 random with >=5 user prompts), de-duplicated, with selection reasons recorded.
- Every selected session was read via `extract`, never via a raw read of the `.jsonl` file.
- Every finding in the final report cites a session id and evidence, per `references/analysis-rubrics.md`.
- Every efficiency recommendation is tagged safe-cut or load-bearing.
- All dollar figures are explicitly framed as counterfactual API-equivalent cost, not real spend.
- `report.md` was written into the same run directory as `metrics.json`/`summary.md`.
- A trend comparison against the previous run's report was attempted, with an honest "no previous run" fallback if none exists.
- The user received a concise summary in chat plus a pointer to the full report file.
</success_criteria>
