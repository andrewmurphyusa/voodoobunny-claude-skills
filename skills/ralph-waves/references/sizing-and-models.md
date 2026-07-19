<overview>
Shared vocabulary for `design-with-fable` (planning) and `ralph-waves` (execution).
An identical copy lives in both skills' `references/`. **If you change one copy, change the other in the same session.**
</overview>

<sizes>
Sizes: **Small ≤ ~1 agent-hour · Medium ~1–3 · Large ~3–8 · Huge = requires Fable.**

Size measures judgment load, not just volume:
- **Small (S):** mechanical, fully specified by the plan; one or two files; no design decisions left.
- **Medium (M):** multi-file; local design decisions inside a fixed contract; the plan pins the contract, the worker picks the internals.
- **Large (L):** owns an architectural seam or cross-cutting concern; needs sustained reasoning but the design doc has already made the hard calls.
- **Huge:** requires frontier-model (Fable-level) judgment — open-ended design, ambiguous requirements, or novel architecture. **A finished plan contains ZERO Huge tasks.** The entire point of planning with Fable is to spend that judgment at design time so S/M/L workers can execute without a hard stop. If a Huge task is genuinely irreducible, it stays in the plan explicitly marked `(Huge — HARD STOP)` with a written justification for why it could not be decomposed.
</sizes>

<model_mappings>
| Size | Claude Code (implementer) | Codex (implementer) |
|---|---|---|
| Small | Claude Haiku (`claude-haiku-4-5`) | GPT-5.6 Luna @ medium effort |
| Medium | Claude Sonnet (`claude-sonnet-5`) @ high effort | GPT-5.6 Terra @ high effort |
| Large | Claude Opus (`claude-opus-4-8`) @ high effort | GPT-5.6 Sol @ high effort |
| Huge | Claude Fable (`claude-fable-5`) @ high effort | **none — HARD STOP** |

**Verifiers run one size below the implementer** (S-task verifiers floor at Haiku / Luna). Verification is independent: the verifier re-derives the checks from the task's Verification text and the design doc — it never just reads the implementer's report.

**Per-task overrides:** a task may carry `[model: <spec>]` after its size, e.g.
`## [ ] T7 — Batch processor (Large) [model: openrouter/deepseek/deepseek-v4]`.
An override names either a Claude model id, a Codex model, or an OpenRouter route. Overrides bind the implementer only; the verifier still follows the one-size-below rule on the task's size using the default table (unless it carries its own `[verifier-model: …]`).
</model_mappings>

<retry_ladder>
An ATTEMPT fails if the implementer reports failure OR the verifier FAILs it — a self-reported failure followed by a verifier FAIL on the same attempt is ONE failed attempt, never two. Count consecutive failed attempts per task at its current size:

1. Failures 1–2 at a size: retry at the SAME size, feeding the failure evidence back (fix-forward).
2. After 2 consecutive failures: escalate one size (S→M→L) and reset the counter.
3. Escalating beyond Large means the task now requires Fable (Huge): under Claude Code, one attempt on Fable if available, then stop and report; under Codex, **CROSS-PROVIDER HARD STOP** — write a handoff note and report.
4. After 2 consecutive failures at the highest reachable size: COMPLETELY FAILED → the wave gate hard-stops.
5. **Infrastructure-disrupted failures never count toward escalation** (AV/PowerShell interference, rate limits, overloads — see the execution skill's infrastructure-errors reference). Retry same size and track separately. Three infrastructure-disrupted failures on one task → HARD STOP with "environment problem".
</retry_ladder>

<conventions>
- **Checkboxes:** every task heading carries one (`## [ ] T4 — Setup automation (Medium)` → `## [x] T4 …` when verified); the task-summary table and the wave table each carry a leading `Done` column of `[ ]`/`[x]`. `[x]*` marks work pre-implemented in the planning session itself.
- **Ownership:** every task has an `**Owns:**` line listing the exact files it may create/modify. Ownership sets are disjoint across tasks in the same wave.
- **Verification:** every task has a `**Verification:**` block of concrete, independently checkable criteria, ending with `**🧑 HUMAN:** none.` or the specific human action required. Tasks needing human action carry 🧑 in their heading.
- **Waves:** tasks grouped so everything inside a wave can run in parallel; each wave has a gate (full-suite checks) that must pass before the next wave dispatches. Human input checkpoints (A-items) sit between waves.
- **Concurrency cap:** maximum 6 concurrent sub-agents (implementers + verifiers + trackers). Queue the excess.
- **Commits:** **Agents never commit — Andrew handles all commits manually.** No `git commit`, `git add`, or staging by any agent, ever. Every task ends with a reported changed-file list instead. Plans must never contain commit instructions.
</conventions>
