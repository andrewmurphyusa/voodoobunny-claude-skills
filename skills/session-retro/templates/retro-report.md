# Session Retro Report

> All dollar figures in this report are **counterfactual estimates of what API billing would have been** for this usage pattern -- the user is on a flat-rate plan, so no real money is being reported here. Treat every `$` figure below as "at API rates," never as actual spend.

## Header

- **Run date**: {{run_date}}
- **Run directory**: `{{run_dir}}` (e.g. `~/.claude/session-retro/runs/{{YYYYMMDD-HHMMSS}}/`)
- **Corpus scanned**: {{n_sessions}} sessions across {{n_projects}} project(s), {{date_range_start}} to {{date_range_end}}, {{total_size_mb}} MB raw JSONL
- **Pricing basis**: {{pricing_basis}} (e.g. "Sonnet 5 intro pricing $2/$10 through 2026-08-31" or "standard rates"; cite `references/pricing.md` cache date: {{pricing_cache_date}})
- **Analyses run**: {{analyses_run}} (full retro / token-efficiency / usage-habits / cost-attribution)

## Executive summary

{{2-5 sentence summary of the single most important takeaway(s) from this run. Lead with the highest-leverage finding, not a recap of methodology.}}

## (a) Token efficiency findings

| Finding | Sessions | Est. $/mo (counterfactual) | Safe cut? | Action |
|---|---|---|---|---|
| {{finding_1}} | {{session_ids_1}} | {{est_monthly_1}} | {{safe_cut_or_load_bearing_1}} | {{recommended_action_1}} |
| {{finding_2}} | {{session_ids_2}} | {{est_monthly_2}} | {{safe_cut_or_load_bearing_2}} | {{recommended_action_2}} |
| {{...}} | | | | |

Notes:
- "Safe cut?" values: `safe cut`, `load-bearing`, or `mixed` (per `references/analysis-rubrics.md` safe-cut vs load-bearing test — the outcome in the transcript was checked before classifying, not just the aggregate metric).
- "Est. $/mo" is a range where precision isn't warranted (see counterfactual honesty rules), e.g. `$2-4/mo`.
- Every row must be traceable to evidence cited in the Methodology section or inline citations below the table.

{{Optional: 1-2 sentences per notable finding with session id + timestamp + short quote, per evidence requirements in analysis-rubrics.md}}

## (b) Habit changes (ranked, top 10)

Ranked by estimated impact (frequency x effect), most impactful first. Only include habits observed across >=2-3 sessions (see small-sample caveats); a single instance is noted as an anecdote, not ranked as a habit.

1. **{{habit_1_title}}** -- {{habit_1_description}}. Evidence: session `{{session_id}}` at `{{timestamp}}` -- "{{short_quote}}". {{Additional occurrences if any.}}
2. **{{habit_2_title}}** -- ...
3. ...
{{... up to 10}}

Explicitly excluded from this section (owned by other tools, see `references/existing-tools.md`): missed `rtk` prefix opportunities (-> `rtk discover`), permission-allowlist candidates (-> `/fewer-permission-prompts`).

## (c) Cost attribution

### Category breakdown

| Category | Est. tokens | Est. $ (counterfactual) | % of total |
|---|---|---|---|
| Input (fresh) | {{tokens}} | {{cost}} | {{pct}} |
| Cache read | {{tokens}} | {{cost}} | {{pct}} |
| Cache write (5m) | {{tokens}} | {{cost}} | {{pct}} |
| Cache write (1h) | {{tokens}} | {{cost}} | {{pct}} |
| Output | {{tokens}} | {{cost}} | {{pct}} |
| Sidechain/subagent | {{tokens}} | {{cost}} | {{pct}} |
| **Total** | {{total_tokens}} | {{total_cost}} | 100% |

### Counterfactuals

- {{"Compacting/restarting at turn N in session X would have saved an estimated $Y (assumption: ...)"}}
- {{"Turn(s) in session X were Haiku-eligible and cost an estimated $Z more than necessary (assumption: ...)"}}
- {{Additional counterfactuals, each with stated assumptions per analysis-rubrics.md.}}

### Cost per completed task

{{Where task boundaries are identifiable: estimated counterfactual $ per completed task/session, to give a per-unit-of-work sense of spend. State assumptions about what counts as "completed."}}

### ccusage cross-check

- ccusage-reported total (ground truth): {{ccusage_total}}
- This report's independently-computed total: {{report_total}}
- Delta: {{delta}} -- {{explanation if >~5%, e.g. differing date range, dedupe differences, sidechain handling}}

## Trend vs previous run

- Previous run: `{{previous_run_dir}}` ({{previous_run_date}})
- {{Directional comparison: total est. cost, top recurring findings that persisted or were resolved, new findings since last run.}}
- {{If no previous run exists: "This is the first run; no trend data available."}}

## Methodology + caveats

- Parser: `scripts/parse_sessions.py scan` over `{{claude_dir}}`, sessions filtered by {{filters_applied}}.
- Sessions read in full via `extract`: {{list of session ids and why selected -- top-N by cost, flagged, random sample}}.
- Pricing basis and cache date: see header.
- Known limitations this run: {{e.g. small sample size, unresolved model strings flagged, any parser edge cases hit}}.
- Reminder: all costs are counterfactual API-rate estimates on a flat-rate plan, not real spend.
