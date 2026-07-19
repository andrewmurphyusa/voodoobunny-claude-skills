# Implementation Plan & Tracking: {{project name}}

Target repo: `{{exact path}}` — all task paths are relative to it.
Plan folder: `{{this folder's path in the Daily repo}}`

## Sizing legend & complexity→model mappings

<!-- source of truth: references/sizing-and-models.md in the design-with-fable skill — keep in sync -->

Sizes: **Small ≤ ~1 agent-hour · Medium ~1–3 · Large ~3–8 · Huge = requires Fable.**

| Size | Claude Code (implementer) | Codex (implementer) |
|---|---|---|
| Small | Claude Haiku (`claude-haiku-4-5`) | GPT-5.6 Luna @ medium effort |
| Medium | Claude Sonnet (`claude-sonnet-5`) @ high effort | GPT-5.6 Terra @ high effort |
| Large | Claude Opus (`claude-opus-4-8`) @ high effort | GPT-5.6 Sol @ high effort |
| Huge | Claude Fable (`claude-fable-5`) @ high effort | **none — HARD STOP** (see orchestrator prompt) |

Verifiers run one size below the implementer (floor: Haiku/Luna). Per-task `[model: …]` overrides bind the implementer only.

## Conventions binding every task

- One task = one sub-agent, touching only that task's `**Owns:**` files.
- **Agents never commit — Andrew handles all commits manually.** No `git commit`, `git add`, or staging by any agent, ever. Every task ends with a reported changed-file list.
- Verification is independent: the verifier re-derives checks from this doc and the design doc, never from the implementer's report.
- Checkbox flips to `[x]` only after verification passes. `[x]*` = pre-implemented during the planning session.
- Tasks needing human action carry 🧑 in the heading and name their A-item.

## Task summary

| Done | ID | Task | Size | Depends on | Wave |
|---|---|---|---|---|---|
| [ ] | T1 | {{short description}} | {{S/M/L}} | — | 1 |
| [ ] | T2 | … | … | {{T-ids / A-items}} | … |

<!-- One row per task. Dependencies name task IDs and A-items (human inputs from doc 05). -->

## [ ] T1 — {{name}} ({{Small|Medium|Large}}){{ [model: …] if overridden}}

**Owns:** `{{file}}`, `{{file}}`.

{{Body: what to build, citing design sections precisely — "Design §4.4: …". Pin anything
a one-size-down model would otherwise guess: exact flags, schemas, edge cases, error handling.}}

**Verification:** {{concrete, independently executable checks a one-size-below verifier can run:
commands, properties to assert, negative cases. Not "review the code".}} **🧑 HUMAN:** none.

<!-- Repeat per task. For Large tasks, prefer a numbered Verification list with a property-based
     check or two. If any task sizes out as Huge: decompose it (pin more contract in the design
     doc, split judgment from mechanics). Only an irreducible Huge stays, as:
     ## [ ] Tn — {{name}} (Huge — HARD STOP)  …plus a written justification. -->

## Definition of done

{{Project-level completion statement: all waves gated green, live checks done, docs current.}}
