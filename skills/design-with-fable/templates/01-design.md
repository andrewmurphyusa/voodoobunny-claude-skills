# Design: {{project name}} ({{one-line shape, e.g. "SMS + AudioPen → cloud store → local pipeline"}})

<!-- The authoritative technical design. Workers execute against THIS document; every decision
     they would otherwise make gets made here. Target repo: state it in the header area. -->

Target repo: `{{exact path, e.g. c:/sourcecode/github/idea-projects-with-tasche/nascent/<project>/}}`

## 0. One-paragraph summary

## 1. Architecture

<!-- Components, data flow, where each piece runs. Diagram (ASCII or mermaid) plus prose. -->

## 2. Contracts

<!-- THE critical section for zero-Huge plans: every cross-component contract pinned exactly —
     schemas (inline JSON Schema or field tables), envelopes, function signatures, file formats,
     directory layouts. A Medium worker must be able to implement against these without asking. -->

## 3. {{major component A}}

### 3.1 …
<!-- Per-component detail: behavior, error handling, edge cases, exact config keys. -->

## 4. {{major component B}}

## 5. Configuration

<!-- Single source of config; every key named with defaults. -->

## 6. Reuse from existing code (the leverage list)

<!-- Exact files/modules to vendor or import, from which repo, and what NOT to touch. -->

## 7. Security posture

<!-- Secrets handling, auth boundaries, what is never logged/echoed, network exposure. -->

## 8. Deliberately not built ({{v1}} scope fence)

<!-- Explicit list of tempting adjacent features that are OUT. This fence is what keeps
     workers from wandering. -->

## 9. Alternatives considered and rejected

<!-- One line each: alternative → why rejected. -->
