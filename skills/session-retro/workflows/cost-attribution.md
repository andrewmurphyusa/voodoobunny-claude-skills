<required_reading>
- `../references/pricing.md` — full pricing table, cache multiplier math, and the Sonnet 5 intro-vs-standard rate note. This workflow must report figures both ways (see step 5).
- `../references/analysis-rubrics.md` — counterfactual-honesty rules (state assumptions, use ranges not false precision) and evidence requirements.
- `../references/existing-tools.md` — ccusage owns ground-truth totals; confirm every figure this workflow produces is an attribution/counterfactual layer on top of ccusage, not a restatement of it.
</required_reading>

<process>
This workflow answers exactly one question: **where did the API-equivalent cost go, and what would it have been under different choices?** ccusage already reports the ground-truth totals — this workflow does not recompute or second-guess those totals; it explains and attributes them, and builds counterfactuals on top.

**Framing reminder for every output artifact:** the user is on a flat-rate plan. Every dollar figure produced by this workflow is a counterfactual — "what this usage would have billed on the API" — never real spend. State this explicitly in the output header, not just once buried in a footnote.

1. **Establish ground truth.** If the user has `npx ccusage` output available (or can run it), treat its totals as authoritative for overall spend/session counts. If not available, note that this workflow's totals come solely from `scripts/parse_sessions.py scan` and may drift slightly from ccusage due to differing dedup/model-resolution assumptions — say so rather than presenting the script's totals as unquestionable ground truth.

2. **Run the scan:** `python scripts/parse_sessions.py scan` (with `--sonnet5-intro` if the analysis window falls within the Sonnet 5 intro pricing period — check `references/pricing.md` for the cutoff date before deciding). Read `summary.md` and `metrics.json` for per-session and per-category cost breakdowns.

3. **Attribute cost to categories**, building a category table from `metrics.json` figures (do not hand-compute — read the script's numbers):
   - **Cache-rewrite waste** — dollar cost of gap-rewrite events (cache expired and had to be rewritten at the 1.25x/2.0x premium instead of read at 0.1x).
   - **Re-read cost** — estimated dollar cost of files read 2+ times, using the token counts the script already attributes to those reads.
   - **MCP/context overhead** — cost attributable to large tool results and elevated baseline context (tool definitions, MCP server instructions) rather than to the substantive conversation, where visible in the extract for sampled sessions.
   - **Everything else** — the remainder, i.e. cost that went toward the actual work product.

   For any category where `metrics.json` doesn't provide a direct figure, extract a small sample of the relevant sessions (`python scripts/parse_sessions.py extract <file>`) to estimate it, and clearly mark the figure as an estimate with its basis.

4. **Build counterfactuals.** For each significant waste category or flagged session, state a specific counterfactual with an explicit, stated assumption and a range rather than false precision, e.g.:
   - "Compacting or restarting the session at request #N (when context hit ~X tokens) instead of continuing to request #M would have saved an estimated $Y-$Z in cache-write premiums, based on the growth rate observed between N and M."
   - "Turns identified as Haiku-eligible (mechanical/simple work per the usage-habits model-mix check, if that analysis is available) cost an estimated $Z more than they would have on Haiku, based on the token counts for those turns at Sonnet vs Haiku rates."

   Every counterfactual must state its assumption plainly (e.g. "assumes the same token volume would have been needed on the cheaper model, which may not hold if quality required redoing the work") and give a range, not a single decimal-precise number.

5. **Report pricing both ways.** Because Sonnet 5 has an introductory rate through 2026-08-31 per `references/pricing.md`, present cost figures for any window touching that period using both the intro rate and the standard post-intro rate, so the report remains useful after the intro period ends. Label clearly which figure is which.

6. **Compute cost-per-completed-task.** For sessions where the extract makes the outcome clear (task completed, abandoned, or handed off), compute an approximate API-equivalent cost per completed task = total session cost / count of tasks that reached a working/shipped state in that session. Note sessions where the outcome is ambiguous rather than forcing a number.

7. **Cross-check against ccusage** where available: note whether this workflow's totals are within a reasonable margin of ccusage's, and if not, flag the discrepancy rather than silently presenting divergent numbers.

8. **Present findings**: category table, counterfactuals list, cost-per-completed-task, and the ccusage cross-check note — all explicitly labeled as counterfactual API-equivalent figures for a flat-rate-plan account. If run standalone (not via `full-retro`), present directly in chat rather than filling the full report template.
</process>

<success_criteria>
- Every dollar figure is explicitly labeled as counterfactual API-equivalent cost, not real spend, starting from the output's header.
- No figure duplicates a ccusage ground-truth total without adding attribution or counterfactual value on top.
- Cost figures were read from `metrics.json`/`summary.md`, not hand-computed, except where explicitly marked as an extract-based estimate with stated basis.
- At least the four required attribution categories (cache-rewrite waste, re-read cost, MCP/context overhead, everything-else) appear in the category table.
- At least one counterfactual is stated with an explicit assumption and a range, not a single false-precision number.
- Sonnet 5 figures for any window touching the intro-pricing period are reported both at intro and standard rates.
- Cost-per-completed-task is computed where the outcome is clear, and explicitly skipped (not guessed) where it isn't.
- A ccusage cross-check was attempted, with discrepancies flagged rather than hidden.
</success_criteria>
