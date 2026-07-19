<overview>
How the ralph-waves orchestrator dispatches implementer and verifier sub-agents: prompt templates, dispatch mechanisms, and per-task model overrides (including non-Anthropic routes).
</overview>

<dispatch_mechanisms>
**Default — Agent tool (in-session sub-agents).** Dispatch with the Task/Agent tool, `subagent_type: general-purpose`, `model:` set from the size table (`haiku`/`sonnet`/`opus`; `fable` only for a sanctioned Huge escalation). Run implementers of one wave concurrently in the background, respecting the 6-agent cap.

**CLI shell-out (for overrides or cross-provider work).** When a task's `[model: …]` override names a model the Agent tool cannot host, shell out and capture output to a file in the scratchpad, then read the report:
- Claude models: `claude --model <model-id> -p --output-format text < prompt.md > report.md`
- Codex models: `codex exec --model <model-id> "$(cat prompt.md)" > report.md`
- OpenRouter routes (`openrouter/<vendor>/<model>`): use any installed OpenAI-compatible agent CLI pointed at OpenRouter, e.g. `codex exec` with `OPENAI_BASE_URL=https://openrouter.ai/api/v1` and `OPENAI_API_KEY=$OPENROUTER_API_KEY`, passing the model id after the `openrouter/` prefix. If no capable CLI is installed, report the override as unsatisfiable and fall back to the size-table default — note the substitution in `build-log.md`.

CLI workers run outside your permission sandbox: give them the same Owns-only and no-commit rules in the prompt, and verify their diff footprint (`git status --porcelain` via a Haiku sub-agent) after they return.
</dispatch_mechanisms>

<implementer_prompt_template>
Every implementer prompt is self-contained (workers have no session context). Assemble:

```
You are implementing ONE task from a reviewed plan. Work only in <target repo path>.

## Task (verbatim from plan doc 02)
<task heading, Owns list, body, Verification block>

## Design context
<the design-doc sections the task body cites, pasted verbatim — not the whole design doc>

## Rules
1. Touch ONLY the files in Owns. If correctness seems to require touching another file, STOP
   and report the conflict instead of editing it.
2. NEVER run git commit, git add, or any staging. Andrew commits manually.
3. Run the task's own tests/checks before reporting done.
4. <PowerShell disruption block from references/infrastructure-errors.md, verbatim>

## Report format
- STATUS: DONE | FAILED | INFRASTRUCTURE-DISRUPTED
- Changed files (full list, paths relative to repo root)
- What you built, in ≤10 lines
- Test/check results (commands + outcomes)
- Anything you were forced to assume
```

On retry after a failure, append `## Previous attempt` with the verifier's FAIL evidence and the prior report — fix-forward, do not restart from scratch unless the verifier said the approach is unsalvageable.
</implementer_prompt_template>

<verifier_prompt_template>
Verifier runs one size below the implementer (floor Haiku). Prompt:

```
You are independently verifying a task another agent claims to have completed. Do NOT trust
its report — re-derive every check yourself. Work read-only except for running tests.

## Task and Verification criteria (verbatim from plan doc 02)
<task section including the Verification block>

## Design context
<the design sections the Verification block cites>

## Changed files claimed
<list from the implementer's report>

## Procedure
1. Confirm every Owns file exists and no files outside Owns were modified
   (git status --porcelain in <target repo>).
2. Execute each Verification criterion literally: run the commands, construct the negative
   cases, check the properties. A criterion you cannot execute is a FAIL with reason
   "unverifiable", not a pass.
3. <PowerShell disruption block, verbatim>

## Report format
- VERDICT: PASS | FAIL
- Per-criterion result with the evidence (command output, file excerpt)
- If FAIL: the minimal description of what the implementer must change
```
</verifier_prompt_template>

<tracker_updates>
Checkbox flips and `build-log.md` appends are small: do them yourself with Edit when idle, or hand them to a Haiku tracker sub-agent when the loop is busy — trackers count against the 6-agent cap.
</tracker_updates>
