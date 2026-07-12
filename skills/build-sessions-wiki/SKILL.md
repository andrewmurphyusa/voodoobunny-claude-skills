---
name: build-sessions-wiki
description: Build or update an LLM-optimized Markdown wiki of Claude Code sessions (verbatim prompts, work summaries, tags/cross-references, pricing-free metrics). Use when asked to build, create, refresh, update, or rebuild the sessions wiki, or to index Claude Code sessions into a wiki.
---

<essential_principles>
**Scripts count, Fable judges.** `scripts/wiki_tools.py` does all enumeration, parsing, token math, and index generation. Fable's job is the LLM-written content only: titles, summaries, outcomes, tags, cross-references. Never hand-compute what the script already outputs, and never hand-write `INDEX.md`/`tags/TAGS.md`/`wiki-meta.json` — `finalize` generates those.

**Shared core.** The pricing-free parsing/dedup/token-math/fingerprint/gap-detection logic lives in `scripts/session_core.py`, imported by `wiki_tools.py` here AND by session-retro's `parse_sessions.py` (via a `sys.path` shim). This is the one canonical parser — the two skills are intentionally coupled so there is no second copy to drift. Edit parsing behavior in `session_core.py`, not in either command script.

**Never read raw session JSONL wholesale.** Session files are large and full of duplicate/streaming noise. Go through `wiki_tools.py metrics` (numbers), `prompts` (verbatim user prompts), and `extract` (condensed transcript). Do not `cat`, `Read`, or `grep` a raw `.jsonl` file.

**No source control, ever.** The target wiki folder may be a git repo. This skill never runs `git add`, `commit`, `push`, `pull`, or conflict resolution there — not even "helpfully". The user owns all source control.

**Never delete session pages.** The wiki may legitimately contain sessions that no longer exist locally (aged out, or indexed on another machine). Pages whose source is missing are history, not garbage.

**`last_refreshed` is the refresh run's START time.** Capture the UTC timestamp before processing begins and pass exactly that to `finalize --started-at`. Sessions modified mid-refresh then get re-picked next run instead of slipping through.

**The wiki is pricing-free.** Metrics stored in pages are token counts only. Never write dollar figures into the wiki; pricing is session-retro's job at read time.
</essential_principles>

<configuration>
Shared config for the sessions-wiki skill family lives at `~/.claude/sessions-wiki/config.json`:

- `default_wiki_dir` — used when the user doesn't name a wiki folder.
- `staleness_hours` — used by the search skills (default 6); this skill only preserves it.

Read/update via the script (never edit the JSON by guesswork):
```
python scripts/wiki_tools.py config get
python scripts/wiki_tools.py config set --key default_wiki_dir --value "D:\wikis\sessions"
python scripts/wiki_tools.py config set --key staleness_hours --value 24
```
</configuration>

<process>
1. **Resolve the wiki folder.**
   - User supplied one → use it. If no `default_wiki_dir` is configured yet, or the user says to make this the default, save it with `config set`.
   - No folder supplied → use `default_wiki_dir` from `config get`.
   - Neither exists → ask the user for a folder, then save it as the default.
   Create the folder (and `sessions/`) if missing. Do NOT `git init` it.

2. **Resolve the time range.**
   - User gave a start time / period ("past 5 days", "since July 1") → convert to `--since <ISO or YYYY-MM-DD>`.
   - User gave nothing → omit `--since`; `plan` automatically falls back to the wiki's `last_refreshed`, and to *all sessions* if the wiki has none yet. Report which from-time was used (`from_time_source` in plan output).
   - User explicitly said "everything"/"full rebuild" → `--all`.

3. **Capture the start time.** `python -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat(timespec='seconds'))"` — hold onto this for step 7.

4. **Run the plan.**
   ```
   python scripts/wiki_tools.py plan --wiki-dir <WIKI> [--since ...|--all] [--project SUB]
   ```
   Work items are sessions with status `new` or `changed`. Skip `unchanged` (already fully indexed). Note `wiki_only_sessions` — informational only, never delete those pages.

5. **Write one page per work item.** For each session, run:
   ```
   python scripts/wiki_tools.py metrics <path>
   python scripts/wiki_tools.py prompts <path>
   python scripts/wiki_tools.py extract <path>        # add --max-text/--max-tool for huge sessions
   ```
   Then write `sessions/<project>/<session_id>.md` following `templates/session-page.md` exactly — frontmatter keys and body section order are a contract (see `references/wiki-format.md`):
   - Frontmatter facts (`source_mtime_epoch`, `source_size`, `machine`, timestamps, cwd, branch) come verbatim from the metrics JSON / plan entry.
   - `title`, `tags`, `## Summary`, `## Outcome`, `## Keywords and cross-references` are LLM-written from the extract; follow the tagging conventions and check `tags/TAGS.md` for existing tags first.
   - `## Prompts` is the `prompts` output pasted unmodified; `## Metrics` is the `metrics` JSON pasted unmodified in a fenced json block.
   - For sessions with subagent transcripts, the extract of the main file plus the metrics (which already include sidechain totals) is normally enough; extract individual subagent files only when the main thread doesn't explain what the subagents did.

6. **Batching for large backfills.** More than ~20 work items: process newest-first in batches and tell the user the progress. Interruption is safe by design — pages already written are detected as `unchanged` on the next run, and `last_refreshed` only advances in step 7. Resume by re-running the skill.

7. **Finalize.**
   ```
   python scripts/wiki_tools.py finalize --wiki-dir <WIKI> --started-at <step-3 timestamp>
   ```
   This regenerates `INDEX.md` and `tags/TAGS.md` from page frontmatter and stamps `wiki-meta.json` with `last_refreshed`.

8. **Report.** Tell the user: wiki folder, from-time used, pages created/updated/skipped, total pages now in the wiki, and an explicit reminder that nothing was committed to source control.
</process>

<script_index>
All deterministic work runs through `scripts/wiki_tools.py` (Python 3, stdlib only; invoke with plain `python` — RTK has no filter for this output shape). Run `python scripts/wiki_tools.py help` for full example-driven usage of every command, or `help <command>` (e.g. `help plan`) for one:

- `config get|set` — shared config (`default_wiki_dir`, `staleness_hours`).
- `status [--wiki-dir DIR]` — last_refreshed + staleness verdict.
- `plan [--wiki-dir DIR] [--since T] [--all] [--last N] [--project SUB]` — JSON work plan; statuses new/changed/unchanged; subagent transcripts included in the fingerprint.
- `metrics <session.jsonl>` — pricing-free per-session metrics JSON (paste verbatim into the page).
- `prompts <session.jsonl> [--max-chars N]` — verbatim human prompts as Markdown (paste verbatim).
- `extract <session.jsonl> [--max-text N] [--max-tool N]` — condensed transcript for Fable to read.
- `finalize --wiki-dir DIR --started-at ISO` — regenerate index/tags, stamp last_refreshed.
</script_index>

<reference_index>
- `references/wiki-format.md` — the full wiki format contract: layout, frontmatter keys, fully-indexed fingerprint, body sections, multi-machine rules, tagging conventions. Required reading before writing pages.
- `templates/session-page.md` — the page template to instantiate per session.
</reference_index>

<testing>
The deterministic logic lives in compute-only functions that return data (in `session_core.py` for parsing/metrics, in `wiki_tools.py` for config/plan/status/index rendering); the `*_command` wrappers just print. Tests target those functions against a committed synthetic fixture — no dependency on live `~/.claude` data. Run:

```
python -m unittest discover -s skills/build-sessions-wiki/tests -p "test_*.py"
```

- `tests/test_session_core.py` — the shared parser: primitives, the pure sub-analyses (gap detection, flags, prompt counting, context growth), and `metrics_from_records` exercised with tiny in-memory record lists (one case per parsing rule, no fixture files needed).
- `tests/test_wiki_tools.py` — wiki-specific: config, staleness, plan/classification, index/tag rendering, and `compute_session_metrics` on the committed fixture.
- `tests/test_contract.py` — cross-skill guard: confirms session-retro imports this same `session_core`, and that the JSONL and wiki cost paths in `parse_sessions.py` produce identical priced records for one fixture. Run it after changing anything in `session_core.py` or either command script. See `tests/README.md`.

session-retro has its own suite (`skills/session-retro/tests/`) for the pricing layer and scan aggregation.
</testing>
