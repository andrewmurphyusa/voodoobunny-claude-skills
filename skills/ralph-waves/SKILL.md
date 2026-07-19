---
name: ralph-waves
description: Executes a design-with-fable plan folder as an autonomous wave-by-wave implementation loop. A clean-context orchestrator dispatches sized sub-agent workers (Haiku for Small, Sonnet for Medium, Opus for Large; Huge is a hard stop), verifies every task with a one-size-below sub-agent, enforces wave gates and a retry/escalation ladder, recovers from infrastructure errors (Avast/PowerShell interference), and never commits. Use when asked to execute, run, build, or resume an implementation plan produced by design-with-fable, or to run Ralph-style autonomous waves.
---

<objective>
Execute an implementation plan wave by wave with the cheapest models that can do each job, while the orchestrator (you) keeps its own context clean and implements nothing itself. All Fable-level judgment was spent at planning time; your job is dispatch, verification, tracking, and knowing when to stop.
</objective>

<quick_start>
1. Read `references/sizing-and-models.md` NOW — sizes, model mappings, retry ladder, conventions. Everything below assumes it.
2. Locate the plan folder (a `design-with-fable` artifact set: docs 01 design, 02 plan, 03 waves, 05 inputs) and the target repo named inside doc 02.
3. Run the `<startup_protocol>`, then the `<execution_loop>`.
4. **Single-task mode:** when asked to run just one task (testing the loop, or an out-of-band fix), run one iteration of steps 3–6 of the loop for that task only — same worker sizing, same independent verification, same tracking updates, no wave gate.
</quick_start>

<essential_principles>
**Context discipline.** You never read implementation files, never write code, never debug directly. Workers and verifiers do all file-touching work and return compact reports. If you catch yourself opening source files to "quickly check", dispatch a sub-agent instead. Your context holds: the plan docs, dispatch state, and reports.

**Sizes are model assignments.** Small→Haiku, Medium→Sonnet, Large→Opus. **Huge = HARD STOP: escalate to Fable if this session can dispatch it, otherwise to Andrew — never attempt Huge work with a smaller model.** Per-task `[model: …]` overrides in doc 02 are honored via `references/worker-dispatch.md`, including non-Anthropic routes (OpenRouter, other agent CLIs).

**Independent verification.** Every task is verified by a sub-agent one size below the implementer, which re-derives the checks from doc 02's Verification text and the design doc — it never trusts the implementer's report. Wave gates get their own verifier run before the next wave dispatches.

**Infrastructure errors are not failures.** Avast/PowerShell interference, rate limits, and overloads (patterns in `references/infrastructure-errors.md`) are INFRASTRUCTURE-DISRUPTED attempts: recover and retry at the same size; they never count toward escalation.

**No commits, ever.** Neither you nor any sub-agent runs `git commit`, `git add`, or staging. Tracking docs accumulate changed-file lists; Andrew commits manually.

**Backpressure.** Maximum 6 concurrent sub-agents (implementers + verifiers + trackers) unless doc 03/04 says otherwise. Queue the excess; a wave's "width" is a request, not a license.
</essential_principles>

<startup_protocol>
Run on EVERY start, including resume:
1. Read docs 02, 03, 05 from the plan folder, plus `av-warnings.md` and `build-log.md` if present. Do not read doc 01 in full — pull design sections on demand into worker prompts.
2. Reconcile checkboxes against reality: for each `[x]` task, spot-check (via a Haiku sub-agent if more than a couple) that its `Owns:` files exist in the target repo; flag mismatches to Andrew before proceeding.
3. Current wave = first wave whose Done box is `[ ]`.
4. Check doc 05's checkpoints gating the current wave. If a `HARD_STOP.md` file exists in the plan folder, stop immediately and report.
5. Report: current wave, dispatchable tasks, gated tasks with their A-items. Then proceed with whatever is not gated; if everything is gated, stop and report what is needed.
</startup_protocol>

<execution_loop>
1. List the current wave's tasks with dependencies satisfied and no unmet human gate (🧑 tasks whose A-items are unsatisfied wait; the rest of the wave proceeds if doc 03 allows).
2. Dispatch one implementer sub-agent per task, concurrently, under the 6-agent cap. Build each prompt per `references/worker-dispatch.md` — self-contained, Owns-only discipline, no-commit rule, infrastructure-monitoring block included verbatim.
3. On each report, dispatch a verifier one size below with the prompt template in `references/worker-dispatch.md`. Verifier verdict is PASS or FAIL with evidence.
4. On FAIL or self-reported failure, apply the retry ladder from `references/sizing-and-models.md`. First classify against `references/infrastructure-errors.md`: infrastructure-disrupted attempts retry same size and never escalate.
5. After each PASS: flip the task's checkbox in doc 02 (heading + summary table), and append to `build-log.md`: task ID, attempts, models used, changed-file list.
6. When all the wave's tasks are verified, run the wave gate from doc 03 via a verifier sub-agent (Sonnet unless the gate involves Large-task seams, then Opus). Gate PASS → flip the wave's Done box, move to the next wave. Gate FAIL → treat as a task-level failure of the responsible task(s); a twice-failed gate is a hard stop.
7. **Pause and report at any wave boundary that has a human gate** — never barrel through a 🧑 checkpoint, even if defaults exist.
</execution_loop>

<hard_stops>
Stop, update tracking docs, and report precisely what is needed to resume, when:
1. A task is or becomes Huge (escalation beyond Large): dispatch to Fable if this session can; otherwise report to Andrew. Never attempt with a smaller model.
2. `HARD_STOP.md` appears in the plan folder.
3. A task is COMPLETELY FAILED (retry ladder exhausted) or a wave gate fails twice.
4. Three infrastructure-disrupted failures on one task, or PowerShell itself is down/quarantined (takes out every agent).
5. The current wave is entirely gated on missing human inputs.
6. Usage/rate limits make progress impossible — write resume state to `build-log.md` first.
</hard_stops>

<reference_index>
All in `references/`:
- **sizing-and-models.md** — sizes, model tables (Claude Code + Codex), overrides, retry ladder, conventions. Shared verbatim with `design-with-fable`; keep the two copies in sync.
- **worker-dispatch.md** — implementer/verifier prompt templates; dispatching via the Agent tool vs CLI shell-outs; per-task model overrides incl. OpenRouter and non-Anthropic CLIs.
- **infrastructure-errors.md** — Avast/PowerShell disruption patterns for this machine, corroboration script, AV-WARNING logging, rate-limit/overload classification, recovery rules.
</reference_index>

<success_criteria>
- Every completed task was implemented by a correctly sized (or overridden) worker and PASSed by an independent one-size-below verifier.
- Checkboxes in docs 02/03 match reality; `build-log.md` has a changed-file list per task and nothing was committed by any agent.
- Waves advanced only through passed gates; every 🧑 boundary paused for Andrew.
- Any stop was one of the enumerated hard stops, reported with exact resume requirements — not a silent stall or a smaller model grinding on Huge work.
</success_criteria>
