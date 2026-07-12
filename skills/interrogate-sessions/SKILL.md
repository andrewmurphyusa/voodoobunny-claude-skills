---
name: interrogate-sessions
description: Answer questions about the most recent N Claude Code sessions or last D days of sessions (by last-modified date), whether or not they are in the sessions wiki. Use when asked to interrogate, review, or answer questions about recent Claude Code sessions and it's unclear or irrelevant whether a wiki exists; routes through the wiki when available and reads sessions directly otherwise.
---

<essential_principles>
**Wiki when possible, source only for the gap.** Fully-indexed sessions are cheaper and faster to answer from wiki pages. Raw-session reading is reserved for sessions the wiki hasn't caught up with (or when no wiki exists) — and always via `wiki_tools.py` subcommands, never by reading raw `.jsonl` files directly.

**The user picks the route.** When a wiki exists, whether to use it — and whether to refresh it first — is the user's call, not an inference. Ask (AskUserQuestion when interactive).

**Cite everything.** Every claim in the answer carries a session id plus either a wiki page path or the session file path, with a timestamp or quoted snippet. Distinguish wiki-sourced facts from live-transcript facts when both appear.

**Sibling-skill dependencies.** Scripts come from `../build-sessions-wiki/scripts/wiki_tools.py` (resolved relative to this SKILL.md). Wiki searching delegates to the `search-sessions-wiki` skill; wiki refreshing delegates to `build-sessions-wiki`. Never reimplement either inline.
</essential_principles>

<process>
1. **Parse the scope.** "Most recent N sessions" → `plan --all --last N`. "Last D days" → `plan --all --since <today minus D days, YYYY-MM-DD>`. Neither stated → default to the last 7 days and say so in the answer. Add `--project <substring>` when the question names a project.

2. **Detect a wiki.**
   ```
   python ../build-sessions-wiki/scripts/wiki_tools.py status
   ```
   (add `--wiki-dir` if the user named one). A wiki exists when `wiki_exists` is true.

3. **No wiki → direct mode.**
   - `python ../build-sessions-wiki/scripts/wiki_tools.py plan --all [--last N|--since D] [--project SUB]` to enumerate in-scope sessions (newest first, subagent transcripts listed).
   - Triage cheaply: run `prompts <path>` per session first — user prompts usually reveal which sessions are relevant to the question.
   - For relevant sessions only, run `extract <path>` (tune `--max-text`/`--max-tool` for big files) and, for quantitative questions, `metrics <path>`.
   - Answer with citations (step 6). Optionally mention that building a wiki (`build-sessions-wiki`) would make future questions cheaper.

4. **Wiki exists → ask the user two things** (one AskUserQuestion round):
   - **Route**: search the wiki first, or go directly to the session files?
   - **If wiki: refresh?** refresh it first, or search it as-is?
   Then:
   - **Wiki + refresh** → invoke the `search-sessions-wiki` skill with the refresh option accepted (it calls `build-sessions-wiki`, then searches). The task collapses entirely to that skill — no manual session reading remains, because after the refresh nothing in scope postdates `last_refreshed`.
   - **Wiki, no refresh** → invoke `search-sessions-wiki` (declining its refresh offer) for everything the wiki covers, AND cover the gap manually: run `plan --since <wiki last_refreshed>` (plus the step-1 `--last`/`--project` narrowing, without `--all`) to list only sessions modified after the wiki's `last_refreshed`, and read those via `prompts`/`extract`/`metrics` as in step 3. Merge both sets of findings into one answer.
   - **Direct** → step 3, ignoring the wiki.

5. **Drill-down rule (both modes).** Wiki pages answer most questions from `## Summary`/`## Outcome`/`## Prompts`/`## Metrics`. Only extract a wiki-covered session's transcript when the page genuinely lacks the asked-for detail and the source file still exists on this machine.

6. **Answer.** Direct answer first; then citations (session id + page path or file path + timestamp/quote); then coverage notes: the scope used (N/D/default), which findings came from the wiki vs live transcripts, and — in the no-refresh path — the wiki's `last_refreshed` and how many gap sessions were read manually.
</process>
