---
name: search-sessions-wiki
description: Answer questions about past Claude Code sessions by searching the sessions wiki built by build-sessions-wiki (e.g. "interrogate my past 5 days of sessions — what was the last step in the Ralph changes and what was the result?"). Use when asked to search, query, or interrogate the sessions wiki, or ask questions about past sessions when a wiki exists. Offers to refresh a stale wiki first.
---

<essential_principles>
**The wiki is the source; cite it.** Every answer must cite the session id, the page path (`sessions/<project>/<id>.md`), and a timestamp or quoted snippet from the page. If the wiki doesn't contain the answer, say so — never fill gaps from memory.

**Check staleness before searching.** The wiki only knows what existed at `last_refreshed`. A stale wiki silently misses recent sessions, so the staleness check in step 2 is mandatory, and every answer must state the wiki's `last_refreshed` when the question could involve sessions newer than it.

**Machine-generated files are read-only.** Never edit `INDEX.md`, `tags/TAGS.md`, `wiki-meta.json`, or the `## Metrics` block of a page. Never run git commands in the wiki folder.

**Sibling-skill dependency.** This skill uses `wiki_tools.py` from the build-sessions-wiki skill (sibling directory: `../build-sessions-wiki/scripts/wiki_tools.py`, resolved relative to this SKILL.md). Refreshing the wiki means invoking the `build-sessions-wiki` skill, not reimplementing it.
</essential_principles>

<process>
1. **Resolve the wiki folder.** User-supplied location if given; otherwise `default_wiki_dir` from `python ../build-sessions-wiki/scripts/wiki_tools.py config get`. If neither resolves to an existing wiki (`wiki-meta.json` present), tell the user there is no wiki yet and offer to run `build-sessions-wiki` first.

2. **Staleness check (mandatory).**
   ```
   python ../build-sessions-wiki/scripts/wiki_tools.py status --wiki-dir <WIKI>
   ```
   If `stale` is true (age exceeds the configured `staleness_hours`, default 6), tell the user how old the wiki is and **offer to refresh it first**. If they accept, invoke the `build-sessions-wiki` skill (Skill tool; or follow `../build-sessions-wiki/SKILL.md` directly if the Skill tool can't reach it), then continue. If they decline, proceed but flag in the final answer that sessions after `last_refreshed` are not covered.

3. **Search the wiki.**
   - Start with `INDEX.md`: filter by any time range in the question (using each entry's `span=`) and scan titles/tags for topical matches.
   - Use `tags/TAGS.md` for topic-first questions ("anything Ralph-related" → the `ralph`/`setup-ralph` tags), and Grep across `sessions/**/*.md` for terms not captured by tags.
   - Open the candidate session pages. `## Summary` and `## Outcome` answer most "what happened / what was the last step and result" questions; `## Prompts` answers "what did I ask"; the `## Metrics` json block answers quantitative questions (tokens, tool counts, flags) — quote it, don't recompute.
   - Follow `## Keywords and cross-references` links to related sessions (continuations often hold the real outcome).

4. **Drill down only if needed.** If a page lacks the detail asked for AND its frontmatter `machine` matches this machine AND `source_path` still exists, run `wiki_tools.py extract <source_path>` for the condensed transcript. Never read raw `.jsonl` directly. If the source is gone or on another machine, answer from the page and say the transcript is no longer available locally.

5. **Answer.** Lead with the direct answer, then cite: session id(s), page path(s), timestamps, and short quotes. State the wiki's `last_refreshed` whenever recency matters or the refresh offer was declined.
</process>

<configuration>
The staleness interval is user-tunable and this skill owns updating it: when the user says the interval doesn't suit them ("make it 1 day", "stop nagging me hourly"), run:
```
python ../build-sessions-wiki/scripts/wiki_tools.py config set --key staleness_hours --value 24
```
Likewise `config set --key default_wiki_dir --value <path>` if they want a different default wiki. Confirm the new value back to them via `config get`.
</configuration>
