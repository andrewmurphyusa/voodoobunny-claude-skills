---
session_id: {{session_id}}
project: {{project}}
machine: {{machine}}
source_path: {{path}}
source_mtime: {{last_modified ISO}}
source_mtime_epoch: {{source_mtime_epoch}}
source_size: {{source_size}}
first_ts: {{first_ts}}
last_ts: {{last_ts}}
indexed_at: {{UTC now ISO}}
title: {{one-line title; prefer the session's ai_titles/builtin_summaries as raw material}}
tags: {{tag1, tag2, tag3 — per tagging conventions in references/wiki-format.md}}
cwd: {{cwd}}
git_branch: {{git_branch}}
---
## Summary

{{3-10 sentences, LLM-written, dense and factual: what the user asked for, what was
done, key decisions, files/systems touched. Optimize for retrieval, not prose style.}}

## Outcome

{{How the session ended: completed / abandoned / interrupted / handed off.
State the LAST step taken and its result explicitly (e.g. "last step: ran pytest —
3 failures in test_foo.py; session ended before fixing them"). List unresolved
errors or open questions.}}

## Prompts (verbatim, {{N}} total)

{{Paste the output of `wiki_tools.py prompts <session.jsonl>` here UNMODIFIED,
minus its own top-level heading line (this section's heading replaces it).}}

## Keywords and cross-references

- keywords: {{comma-separated retrieval keywords beyond the frontmatter tags}}
- related: {{links like sessions/<project>/<id>.md — one per line with a short
  reason ("continuation of", "same bug as", "prerequisite for"); omit if none}}

## Metrics (machine-generated, pricing-free)

```json
{{verbatim output of `wiki_tools.py metrics <session.jsonl>` — do not edit}}
```
