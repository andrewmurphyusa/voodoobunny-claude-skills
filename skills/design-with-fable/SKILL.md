---
name: design-with-fable
description: Turns a project idea or proposal into a complete Fable-grade planning artifact set - optional research doc, design doc, sized implementation plan (S/M/L/Huge) with independent verification, concurrency waves with gates, an orchestrator prompt runnable by Claude Code or Codex, a human-inputs doc with stage gates, and an effort comparison. Use when planning a project or feature that will be executed by an orchestrated multi-agent loop (ralph-waves), or when asked to design, plan, or produce a plan folder for a project idea.
---

<objective>
Produce the full planning artifact set for a project so that cheaper models can execute it without frontier-model judgment. The designing model spends all the hard judgment now — architecture, contracts, decomposition, verification design — so the execution loop (`ralph-waves`) runs on Haiku/Sonnet/Opus (or Luna/Terra/Sol) workers with **zero Huge tasks** and no hard stops except deliberate human gates.
</objective>

<quick_start>
1. Read `references/sizing-and-models.md` NOW — it defines sizes, model mappings, retry ladder, and conventions used by every artifact.
2. Identify: the idea/proposal (doc or conversation), the target project repo, and today's date.
3. Create the plan folder in the Daily repo: `C:/sourcecode/github/Daily/<YYYY>/<MM>/<YYYY-MM-DD> - Fable - <topic> plans/`.
4. Follow <process>. Each artifact copies its template from `templates/` and fills it.
</quick_start>

<artifact_set>
Fixed numbering; skip 00 when no research is needed (do not renumber the rest):

| # | File | Template |
|---|---|---|
| 00 | `00 - research - <topic>.md` (optional) | templates/00-research.md |
| 01 | `01 - design - <topic>.md` | templates/01-design.md |
| 02 | `02 - implementation plan and tracking.md` | templates/02-implementation-plan.md |
| 03 | `03 - concurrency waves and dependency graph.md` | templates/03-waves-and-graph.md |
| 04 | `04 - orchestrator prompt.md` | templates/04-orchestrator-prompt.md |
| 05 | `05 - Andrew inputs needed.md` | templates/05-inputs-needed.md |
| 06 | `06 - effort comparison.md` | templates/06-effort-comparison.md |
</artifact_set>

<process>
**Step 1 — Intake.** Establish scope from the proposal and conversation. Confirm the target project repo (new projects usually go under `c:/sourcecode/github/idea-projects-with-tasche/nascent/<project>/`). Decide whether a research doc is warranted: only when the design depends on external facts you do not already hold (service pricing, API capabilities, library landscape). If requirements are genuinely ambiguous on a decision that changes the architecture, ask; otherwise proceed with defaults and record them as D-items in doc 05.

**Step 2 — Research (optional, doc 00).** Dispatch parallel Sonnet-level sub-agents, one per research question, with tightly scoped prompts. Synthesize into doc 00 yourself; keep sources. Never let a sub-agent write the doc directly.

**Step 3 — Design (doc 01).** The authoritative technical design. Must contain: architecture; every cross-component **contract** (schemas, envelopes, signatures) pinned exactly; security posture; a reuse/leverage list of existing code; an explicit **scope fence** ("Deliberately not built — v1"); alternatives considered and rejected. Every decision a worker would otherwise have to make gets made here — this is where zero-Huge is won or lost.

**Step 4 — Implementation plan (doc 02).** Decompose into tasks T1, T2, …:
- Size each task per `references/sizing-and-models.md`. **If any task comes out Huge, decompose it** — pin more contract in doc 01, split the judgment from the mechanics — until none remain. An irreducible Huge task stays only with a written justification and an explicit `(Huge — HARD STOP)` marker.
- Every task: heading checkbox, size, optional `[model: …]` override, `**Owns:**` disjoint file list, body citing design sections (`Design §4.4: …`), `**Verification:**` with concrete independent checks, `**🧑 HUMAN:**` line.
- Include a verification design a one-size-below model can actually execute (commands to run, properties to assert — not "review the code").

**Step 5 — Waves + dependency graph (doc 03).** Build the dependency edge list from `Owns:`/consumes relationships, group into maximal parallel waves, write a per-wave gate (full-suite checks, cross-task consistency checks), and place human input checkpoints between waves.

**Step 6 — Orchestrator prompt (doc 04).** Self-contained and pasteable into a fresh Claude Code or Codex session. It must not depend on this skill being installed: include (or point at doc 02's copies of) the model mapping, retry ladder, concurrency cap, tracking rules, hard-stop conditions, and the PowerShell/AV disruption monitoring block from the template.

**Step 7 — Inputs needed (doc 05).** D-items (decisions, defaults fine, zero minutes) then A-items (actions only Andrew can do), each tagged with the wave it gates and a time estimate, with a fallback/default and a "how to signal" mechanism.

**Step 8 — Effort comparison (doc 06).** Options: Claude Code orchestrated, Codex orchestrated, both providers, and "the designing model just builds it now in this session". Each gets Agent effort / Wall clock / Risk notes, then a recommendation.

**Step 9 — Report.** List the created files and the open D/A-items. Do not commit anything.
</process>

<hard_rules>
- **Zero Huge tasks** is the quality bar for doc 02. Huge work belongs in this planning session, not in the plan.
- **Never include commit instructions in any generated artifact.** Every plan states: agents never commit; Andrew commits manually; tasks end with a changed-file list.
- Plan docs go to the dated Daily-repo folder; implementation is planned **in the target project repo** — the plan's paths are target-repo-relative.
- Model mappings, sizes, retry ladder, and conventions come verbatim from `references/sizing-and-models.md`; do not restate them differently per document.
- If you (the planning model) implement anything in-session while designing, mark those tasks `[x]*` in doc 02 rather than omitting them.
</hard_rules>

<success_criteria>
- Plan folder exists under `Daily/<YYYY>/<MM>/` with artifacts 01–06 (00 optional), numbered per <artifact_set>.
- Doc 02 has zero unjustified Huge tasks; every task has a checkbox, size, Owns list, design-section citations, independent Verification, and a 🧑 line.
- Doc 03's waves cover every task exactly once; every wave has a checkbox and a gate; dependency edge list matches doc 02.
- Doc 04 runs standalone in either provider and repeats the hard-stop + no-commit rules.
- Doc 05 covers every 🧑 marker and every external prerequisite; doc 06 ends in a recommendation.
- Nothing was committed.
</success_criteria>
