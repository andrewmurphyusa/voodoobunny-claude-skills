<required_reading>
- `../references/analysis-rubrics.md` — habit-mining rubric and evidence requirements (session id + timestamp + quote for every observation).
- `../references/existing-tools.md` — confirm before writing any finding that it isn't already `rtk discover` or `/fewer-permission-prompts` territory (see explicit exclusion below).
</required_reading>

<process>
This workflow answers exactly one question: **how could the user work better with Claude Code?** It is purely semantic — no token/cost math belongs here. If a finding is really about token spend, it belongs in `token-efficiency.md`; if it's really about dollar attribution, it belongs in `cost-attribution.md`.

**Explicit exclusion:** do NOT re-derive or restate what `rtk discover` already finds (missed RTK-prefixed command opportunities) or what `/fewer-permission-prompts` already finds (recurring permission prompts that could be pre-allowlisted). If a candidate observation is really "the user could have used `rtk <cmd>` here" or "this permission prompt recurs," drop it — those tools own that territory.

1. **Run the scan** (if not already run this session): `python scripts/parse_sessions.py scan` (the configured sessions wiki is used automatically when present; `--wiki-dir`/`--no-wiki` override). Read `summary.md` for the session list and pick a spread across projects and time, not just the most expensive sessions — habits show up in ordinary sessions as much as expensive ones. Include at least a few of the largest-by-turn-count sessions (`MANY_TURNS` flag) since long back-and-forths are rich in habit signal.

2. **Read each selected session.** For `"source": "wiki"` records, the wiki page is unusually well-suited to habit mining — `## Prompts` holds every user prompt verbatim (repeated instructions and corrections live there) and `## Outcome` records abandoned/restarted work — so read the page first and use `extract` only when turn-by-turn flow matters (e.g. distinguishing a genuine clarification from a correction). For `"source": "jsonl"` records, run `python scripts/parse_sessions.py extract <session.jsonl>`. Read across multiple sessions before drawing any pattern — a single occurrence is an anecdote, not a habit.

3. **Mine for these specific patterns across sessions:**
   - **Repeated instructions** — the same guidance, preference, or constraint given by the user in multiple sessions (e.g. restating a coding convention, a file-naming rule, a "always do X" instruction). Each repetition is evidence the instruction isn't durably captured anywhere. Recommend a specific destination: a `CLAUDE.md` addition (if it's a standing preference) or a new/extended skill (if it's a repeated multi-step task).
   - **Corrections** — turns where the user says something equivalent to "no, I meant..." / "that's not what I wanted" / re-explains after a wrong turn. Note what the initial ambiguity was and what would have prevented it (e.g. the user's first message could have included the constraint that only surfaced after correction).
   - **Clarification round-trips** — cases where Claude asked a clarifying question that could have been pre-empted by the user front-loading that detail in the original prompt. Distinguish this from cases where the clarifying question was genuinely necessary (information Claude had no way to know in advance) — only the former is an actionable habit finding.
   - **Abandoned or restarted work** — sessions or sub-threads where the user changed direction mid-task, dropped a task without finishing, or started a fresh session to redo something from an earlier one. Note the apparent cause if visible in the transcript (bad initial approach, changed requirements, session got too unwieldy).
   - **Model-mix opportunities** — turns that used a more expensive model for work that reads as clearly appropriate for a cheaper one (e.g. mechanical formatting, simple lookups, boilerplate generation on a top-tier model), or the reverse — a cheap/fast model used for work that needed more capability and had to be redone. This is a semantic judgment call about task complexity, not a cost calculation — leave the dollar sizing to `cost-attribution.md` if the user wants both.

4. **Write every observation with:** the session id(s) it was observed in (habits should ideally cite 2+ occurrences across sessions to count as a "habit" rather than a one-off; one-offs can still be noted but flagged as single-occurrence), the timestamp/request index, and a quoted or closely-paraphrased snippet as evidence, per `references/analysis-rubrics.md`.

5. **Rank and present** the findings by estimated leverage (how much friction or rework it caused, and how easy the fix is), not by raw occurrence count alone. If this workflow is being run standalone (not via `full-retro`), present directly in chat rather than filling the full report template.
</process>

<success_criteria>
- No token-count or dollar-cost math appears in this workflow's output — it is purely semantic/behavioral.
- No finding duplicates `rtk discover` or `/fewer-permission-prompts` territory.
- Sessions were read via their wiki page or `extract`, never a raw `.jsonl` read.
- Multiple sessions were sampled, not just the single most expensive one — habits require cross-session evidence.
- Each of the five pattern categories (repeated instructions, corrections, clarification round-trips, abandoned/restarted work, model-mix opportunities) was explicitly considered.
- Every finding cites session id(s), timestamp/request index, and evidence; single-occurrence observations are labeled as such.
- Recommendations point to a concrete destination (CLAUDE.md addition, new/extended skill, workflow change) rather than a vague "communicate better."
</success_criteria>
