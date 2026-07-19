<overview>
Infrastructure errors are environment problems, not task failures. They are classified as INFRASTRUCTURE-DISRUPTED attempts: retried at the same size, tracked separately, and **never counted toward the escalation ladder**. Three infrastructure-disrupted failures on one task → HARD STOP ("environment problem"), because grinding a broken environment wastes budget and produces misleading failure counts.
</overview>

<powershell_disruption_block>
Include this block VERBATIM in every implementer and verifier prompt (it is referenced by the templates in worker-dispatch.md):

```
Avast Free on this machine intermittently blocks PowerShell — it has previously quarantined
powershell.exe itself. Watch for: commands dying with no output or NTSTATUS-style exit codes
(e.g. -1073741510); "blocked by your antivirus software" / PSSecurityException text; "Access
is denied" on a file you just created; files that vanish right after being written; PowerShell
failing to start at all (report that IMMEDIATELY — it takes down every agent). If you see any
of these, log a line to av-warnings.md in the plan folder in the format
  AV-WARNING: <ISO timestamp> <task id> <one-line description>
and report your attempt as INFRASTRUCTURE-DISRUPTED, not FAILED.
```
</powershell_disruption_block>

<corroboration>
When an AV-WARNING is logged and you need to confirm it was Avast (e.g. before a hard stop), dispatch a Haiku sub-agent to run:

```powershell
Get-ChildItem "C:\ProgramData\Avast Software\Avast\report" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime
Get-ChildItem "C:\ProgramData\Avast Software\Avast\chest" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime
```

Fresh entries (minutes old) in report/chest logs coinciding with the disrupted attempt = corroborated AV interference. A freshly quarantined `powershell.exe` (chest entry) is an immediate HARD STOP — no agent can run.

Mitigation to suggest to Andrew on AV hard stops: the Avast exclusions script from `Daily/2026/07/2026-07-12 - 002 - Powershell script to add exclusions for Claude Code + Codex + VS Code extensions.md`.
</corroboration>

<other_infrastructure_classes>
Classify by matching worker/CLI output (all major CLIs exit 1 for every error type, so string-match):

| Class | Patterns | Recovery |
|---|---|---|
| RATE_LIMIT | `rate_limit_error`, `rate_limit_exceeded`, `429`, "please slow down" | Exponential backoff (2s, 4s, … cap 60s), then redispatch same size |
| OVERLOADED | `overloaded_error` | Wait ~45s, redispatch; after 3, treat as RATE_LIMIT |
| USAGE_EXHAUSTED | "usage limit", "5-hour window", "weekly limit", `RESOURCE_EXHAUSTED` | HARD STOP class 6: write resume state to build-log.md, report when the window resets |
| AUTH_FAILURE | `authentication_error`, "Invalid API key", "login required" | HARD STOP immediately — needs Andrew |
| AV_DISRUPTION | patterns in the block above, NTSTATUS exit codes (−1073741510 etc.), vanishing files | Retry same size after corroboration check; 3 strikes → HARD STOP |
| CONTEXT_TOO_LONG | `context_length_exceeded`, "maximum context length" | Not infrastructure: the worker prompt is overloaded — trim design context to only cited sections and retry (counts as a real attempt if the trimmed retry fails) |

Anything unmatched is a REAL failure and feeds the retry ladder.
</other_infrastructure_classes>

<distinguishing_rule>
Before counting any failure toward escalation, ask: "Would this identical attempt plausibly have succeeded on a healthy machine?" If yes (AV killed the shell, API throttled, model overloaded) it is infrastructure. If the worker produced wrong code, failed its checks, or misread the task, it is real. When ambiguous, check `av-warnings.md` timestamps and run the corroboration script; unresolved ambiguity counts as REAL (escalation is cheaper than infinite retries on a genuinely failing task).
</distinguishing_rule>
