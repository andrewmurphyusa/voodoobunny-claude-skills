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
```

Or equivalently as CLI commands (outside Claude Code):

```
claude plugin marketplace add andrewmurphyusa/voodoobunny-claude-skills
claude plugin install proposal-evolution@voodoobunny-claude-skills
claude plugin install article-fact-checker@voodoobunny-claude-skills
```

## Skills

### proposal-evolution
Converts a project proposal into a prompt optimized for the taches `create-meta-prompts` skill. Bridges the gap between an initial idea and a full research → plan → implement pipeline.

### article-fact-checker
Evaluates the factual reliability of any article. Accepts article text, a URL, or both. Checks historical and current facts, quote accuracy, numerical claims, whether cited sources actually support what the article claims they support, and whether the article uses language designed to suppress critical thinking. Returns a structured report with per-claim verdicts, reliability scores, and evidence citations.
