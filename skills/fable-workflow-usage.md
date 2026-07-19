# Using `design-with-fable` + `ralph-waves`

Two halves of one workflow, sharing a single vocabulary (sizes S/M/L/Huge, waves, gates,
model mappings). The planning skill spends frontier-model judgment once; the execution skill
runs the result on cheap models.

## Invoking `design-with-fable` (planning)

Run it in a session with the strongest model you have access to (that's the point):

> Use the design-with-fable skill on this proposal: <paste or path to proposal doc>.
> Target repo: c:/sourcecode/github/idea-projects-with-tasche/nascent/<project>/

Output: a dated plan folder `Daily/<YYYY>/<MM>/<date> - <model> - <topic> plans/` containing
docs 00 (research, optional) through 06 (effort comparison). Review it, answer the D-items in
doc 05, prepare A-items as the waves reach them. **You commit the plan folder manually.**

## Invoking `ralph-waves` (execution)

In a fresh Claude Code session (a Sonnet orchestrator is fine — the plan carries the judgment):

> Use the ralph-waves skill to execute the plan folder at <path>. Resume from current state.

Or without the skill installed: paste the plan's `04 - orchestrator prompt.md` into any
Claude Code or Codex session — it is the portable equivalent.

Single-task test: "Use ralph-waves in single-task mode on T4 of <plan folder>."

## How the output feeds forward

| design-with-fable artifact | ralph-waves use |
|---|---|
| 01 design | Pasted section-by-section into worker prompts (never read whole by orchestrator) |
| 02 implementation plan | Task source: sizes → worker models, Owns → file discipline, Verification → verifier script, heading checkboxes → progress state |
| 03 waves + graph | Dispatch order, concurrency, wave gates, human checkpoints |
| 05 inputs needed | Which tasks pause for you (A-items); D-item defaults |
| build-log.md (created during run) | Your manual-commit shopping list: changed files per task |

## Invariants both skills enforce

- Zero Huge tasks in a finished plan; Huge at runtime = hard stop (Fable or you — never a smaller model).
- Verifier one size below implementer, always independent.
- Max 6 concurrent sub-agents; retries never escalate on infrastructure (Avast/PowerShell) errors.
- **No agent ever commits — you commit manually.**

## Maintenance

`references/sizing-and-models.md` exists identically in both skills. Change one → change both
in the same commit.
