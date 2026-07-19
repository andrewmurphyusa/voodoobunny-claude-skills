# Concurrency Waves & Dependency Graph: {{project name}}

## Dependency graph

<!-- ASCII or mermaid — whichever renders the actual shape more clearly. ALSO always include
     the compact edge list; the orchestrator parses that, not the picture. -->

```
{{ASCII diagram, e.g.:
T1 scaffold ──┬─► T3 function ──┬─► T11 live smoke 🧑
              ├─► T4 setup ─────┘
T2 vendor ────┴─► T6 packs}}
```

Full edge list: {{T3←T1 · T4←T1 · T6←{T1,T2} · T11←{T3,T4,A1,A2} · …}}

## Waves

| Done | Wave | Tasks (all parallel within a wave) | Width | Gate to advance |
|---|---|---|---|---|
| [ ] | 1 | {{T1 (S), T2 (M)}} | 2 | {{all verified; full test suite green}} |
| [ ] | 2 | … | … | … |

<!-- Width = number of implementer agents the wave wants; the concurrency cap (6 total
     sub-agents incl. verifiers) still applies — the orchestrator queues the excess.
     Human-gated tasks are bold with 🧑 and may lag their wave when the gate note says so. -->

**Human input checkpoints:** {{between which waves each A-item from doc 05 must land, e.g.
"A1, A2 before Wave 3 dispatch of T11; A3, A4 before Wave 5." State what may proceed without them.}}

**Per-wave gate details:**

**Wave 1 gate**
1. {{Full-suite command(s) and expected result — e.g. `pytest` green including new tests; zero existing tests modified (git diff of tests/ shows only additions).}}
2. {{Per-task verifications passed (see plan doc 02).}}
3. {{Cross-task consistency checks — contracts exported match what next wave's consumers import.}}

<!-- One gate block per wave. Gates are run by verifier sub-agents before the wave's Done
     checkbox flips. A twice-failed gate is a hard stop. -->

**Notes for the orchestrator:** {{anything wave-specific: which tasks may lag, cost discipline
(no live cloud mutations before Tn), repos that must never be modified.}}
