# Analysis rubrics

Rules for turning parser output (`metrics.json`, `summary.md`, `extract` transcripts) into qualitative findings. These rubrics exist to keep judgment honest and evidence-backed -- apply them in every workflow, not just cost-attribution.

## Flat-rate framing (applies everywhere)

**The user is on a flat-rate plan.** Every dollar figure this skill produces is **counterfactual** -- "what the API would have billed for this usage pattern" -- not real spend, not a real bill, not money actually charged. Never phrase a finding as if money changed hands ("this session cost \$4.20"); phrase it as an estimate ("this session would have cost an estimated \$4.20 at API rates"). This framing must appear in the report header and should color the tone of every cost claim: these are efficiency signals, not a budget.

## Safe-cut vs load-bearing test

Every efficiency finding that recommends reducing token spend must be classified as one of:

- **Safe cut** -- the spend did not materially contribute to the session reaching a successful outcome. Test: look at the transcript around the flagged spend and check the *outcome* -- did removing/avoiding it plausibly still get the task done? Examples: a file re-read 4 times with no edits in between and no new information gained; a gap-rewrite triggered by an idle period with no intervening decision that needed the reloaded context.
- **Load-bearing** -- the spend was necessary for the task's success and cutting it would risk the outcome. Examples: a large tool result that was genuinely needed to make a correct decision; re-reading a file after it was edited by another process; a long context that reflects genuinely complex, single-threaded work.

**Never classify a finding without checking the actual outcome in the transcript.** A pattern that looks wasteful in aggregate metrics (e.g. "5 reads of the same file") can be load-bearing if each read followed an edit. Pull the relevant `extract` output and confirm before tagging.

## Habit-mining rubric

For usage-habits analysis, look across multiple sessions (not just one) for:

- **Repeated instructions** -- the same guidance given to Claude more than once across sessions -> candidate for CLAUDE.md or a project-level skill/rule addition.
- **Corrections** -- user messages that walk back or redirect a prior assistant action ("no, I meant...", "don't do X, do Y instead") -> signal that the initial ask was under-specified; note what would have front-loaded the missing spec.
- **Clarification round-trips** -- Claude asking a question that could have been pre-answered in the original prompt -> same fix, front-load the answer.
- **Abandoned/restarted work** -- sessions where a task is started, dropped, and later restarted from scratch -> note the apparent cause if visible (scope change, lost context, error).
- **Model-mix opportunities** -- turns that used a more expensive model for work that a cheaper model plausibly could have handled equally well (simple lookups, formatting, boilerplate).

Do not restate findings that belong to `rtk discover` (missed rtk-prefix opportunities) or `/fewer-permission-prompts` (permission allowlist candidates) -- see `existing-tools.md`.

## Counterfactual honesty rules

- **State assumptions explicitly.** Any counterfactual ("would have cost \$X less", "compacting here would have saved \$Y") must name the assumption behind it (e.g. "assumes the re-read tokens would not have been needed again").
- **Give ranges, not false precision.** Token-to-dollar counterfactuals are estimates built on approximate cache math and substring model matching -- report a range (e.g. "\$2-4/month") rather than a single decimal-precise figure unless the underlying number is a direct sum from `metrics.json` with no judgment applied.
- **Don't stack unverifiable assumptions.** A counterfactual chain of "if X, then Y, then Z" compounds uncertainty fast -- prefer single-step counterfactuals tied directly to one observed event.

## Evidence requirements

Every finding -- efficiency, habit, or cost -- must cite:

1. **Session id** (filename/uuid).
2. **Timestamp** of the relevant request(s).
3. **A short quote or concrete data point** from the transcript or metrics (e.g. the actual re-read count, the actual gap duration, a short excerpt of the repeated instruction).

A finding without all three is not ready to report -- go back to `extract` output and find the citation, or drop the finding.

## Small-sample caveats

- With a 20-session corpus (or similar small N), a single outlier session can dominate aggregate stats -- call out when a "top finding" is driven by one session rather than a pattern.
- Habit-mining findings need repetition across **at least 2-3 sessions** before being reported as a habit; a single instance is an anecdote, not a pattern -- note it as such if included at all.
- Random-sample sessions exist specifically to catch what top-N-by-cost sampling misses (routine, non-expensive sessions) -- don't skip reading them even when they look unremarkable in the metrics.
