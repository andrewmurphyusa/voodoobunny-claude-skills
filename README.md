# voodoobunny-claude-skills

The two-step install on any machine is:


# Step 1: register the marketplace
```
/plugin marketplace add andrewmurphyusa/voodoobunny-claude-skills
```

# Step 2: install the plugin from it
```
/plugin install proposal-evolution@voodoobunny-claude-skills
/plugin install article-fact-checker@voodoobunny-claude-skills
/plugin install session-retro@voodoobunny-claude-skills
/plugin install design-with-fable@voodoobunny-claude-skills
/plugin install ralph-waves@voodoobunny-claude-skills
```

Or equivalently as CLI commands (outside Claude Code):

```
claude plugin marketplace add andrewmurphyusa/voodoobunny-claude-skills
claude plugin install proposal-evolution@voodoobunny-claude-skills
claude plugin install article-fact-checker@voodoobunny-claude-skills
claude plugin install session-retro@voodoobunny-claude-skills
```

## Skills

### proposal-evolution
Converts a project proposal into a prompt optimized for the taches `create-meta-prompts` skill. Bridges the gap between an initial idea and a full research → plan → implement pipeline.

### article-fact-checker
Evaluates the factual reliability of any article. Accepts article text, a URL, or both. Checks historical and current facts, quote accuracy, numerical claims, whether cited sources actually support what the article claims they support, and whether the article uses language designed to suppress critical thinking. Returns a structured report with per-claim verdicts, reliability scores, and evidence citations.

### design-with-fable
Turns a project idea or proposal into a complete planning artifact set: optional research doc, design doc, sized implementation plan (S/M/L/Huge) with independent verification sub-tasks, concurrency waves with gates, an orchestrator prompt runnable by Claude Code or Codex, a human-inputs doc with stage gates, and an effort comparison. The goal of a good plan is zero Huge tasks — frontier-model judgment is spent at planning time so cheaper models can execute. Pairs with `ralph-waves`; see `skills/fable-workflow-usage.md`.

### ralph-waves
Executes a `design-with-fable` plan folder as an autonomous wave-by-wave implementation loop: a clean-context orchestrator dispatches sized sub-agent workers (Haiku/Sonnet/Opus; Huge = hard stop), verifies every task with an independent one-size-below sub-agent, enforces wave gates and a retry/escalation ladder, recovers from infrastructure errors (Avast/PowerShell interference), and never commits.

### session-retro
Analyzes past Claude Code session transcripts for token efficiency, usage habits, and API-equivalent cost attribution. A deterministic Python parser (stdlib only) aggregates the raw session JSONL into compact metrics and a summary; Claude then reads condensed extracts of selected sessions to attribute causes, propose counterfactuals, and tag each recommendation as a safe cut or load-bearing spend. Complements — never duplicates — counters like ccusage. All analysis stays local.
