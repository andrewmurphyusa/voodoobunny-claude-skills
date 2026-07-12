#!/usr/bin/env python3
"""
wiki_tools.py -- deterministic helper for the sessions-wiki skill family
(build-sessions-wiki, search-sessions-wiki, interrogate-sessions).

"Scripts count, Fable judges": this script does all enumeration, parsing,
token math, and index regeneration. Titles, summaries, and tags are written
by the model into the session pages; this script never invents content.

All metrics produced here are PRICING-FREE (token counts only). Dollar
figures are the session-retro skill's job -- it applies its own, current
pricing table to the token buckets stored in the wiki. That way wiki pages
built months ago never bake in stale prices.

Subcommands:

  config    Get/set shared config (~/.claude/sessions-wiki/config.json):
            default_wiki_dir, staleness_hours.
  status    Report a wiki's last_refreshed date and whether it is stale
            relative to the configured staleness_hours.
  plan      Enumerate local session JSONL files (by last-modified date,
            including subagent transcripts), compare against existing wiki
            pages, and emit a JSON work plan: new / changed / unchanged.
  metrics   Emit pricing-free per-session metrics JSON for one session file
            (tokens by model, prompts, gap events, repeat reads, flags, ...).
  prompts   Emit all human prompts of one session, verbatim, as Markdown.
  extract   Emit a condensed, cheap-to-read transcript of one session.
  finalize  Regenerate INDEX.md and tags/TAGS.md from session page
            frontmatter and stamp wiki-meta.json with last_refreshed
            (= the refresh run's START time, passed via --started-at).

Python 3, standard library only. Never commits anything to source control.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Shared, pricing-free core (parsing, dedup, token math, fingerprint, metrics,
# gap detection, transcript rendering). session_core.py lives beside this file.
from session_core import (  # noqa: E402
    FILE_ENCODING_KWARGS,
    FORMAT_VERSION,
    compute_session_metrics,
    find_session_files,
    parse_frontmatter,
    parse_ts,
    read_jsonl_file,
    read_session_records,
    render_extract,
    render_prompts_markdown,
    collect_prompts_from_records,
    session_source_stat,
    utc_now_iso,
)

DEFAULT_CONFIG = {"default_wiki_dir": None, "staleness_hours": 6}


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def default_config_path() -> Path:
    return Path("~/.claude/sessions-wiki/config.json").expanduser()


def load_config(config_file: str | None) -> dict:
    path = Path(config_file).expanduser() if config_file else default_config_path()
    cfg = dict(DEFAULT_CONFIG)
    if path.is_file():
        try:
            with open(path, **FILE_ENCODING_KWARGS) as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"WARNING: could not read config {path}: {e}", file=sys.stderr)
    return cfg


def coerce_config_value(raw: str):
    """Coerce a raw CLI string to int, then float, then None (for null/none/''),
    else leave it as a string. Pure -- unit-tested directly."""
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if raw.lower() in ("null", "none", ""):
        return None
    return raw


def config_set(config_path: Path, cfg: dict, key: str, value) -> dict:
    """Apply key=value to cfg and persist to config_path. Returns the updated
    cfg. No printing; caller reports."""
    cfg[key] = value
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", **FILE_ENCODING_KWARGS) as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg


def config_command(args):
    path = Path(args.config_file).expanduser() if args.config_file else default_config_path()
    cfg = load_config(args.config_file)

    if args.action == "get":
        if args.key:
            print(json.dumps({args.key: cfg.get(args.key)}, ensure_ascii=False))
        else:
            print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return

    # set
    if not args.key or args.value is None:
        print("ERROR: config set requires --key and --value", file=sys.stderr)
        sys.exit(2)
    value = coerce_config_value(args.value)
    config_set(path, cfg, args.key, value)
    print(json.dumps({"config_file": str(path), args.key: value}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# wiki page frontmatter + meta  (parse_frontmatter comes from session_core)
# ---------------------------------------------------------------------------

def collect_wiki_pages(wiki_dir: Path) -> dict:
    """Map session_id -> {page metadata} for every sessions/**/*.md page."""
    pages = {}
    sessions_dir = wiki_dir / "sessions"
    if not sessions_dir.is_dir():
        return pages
    for md in sorted(sessions_dir.rglob("*.md")):
        fm = parse_frontmatter(md)
        if not fm or "session_id" not in fm:
            continue
        try:
            mtime_epoch = int(fm.get("source_mtime_epoch", "-1"))
        except ValueError:
            mtime_epoch = -1
        try:
            size = int(fm.get("source_size", "-1"))
        except ValueError:
            size = -1
        pages[fm["session_id"]] = {
            "page": str(md.relative_to(wiki_dir)).replace("\\", "/"),
            "abs_page": str(md),
            "project": fm.get("project", ""),
            "machine": fm.get("machine", ""),
            "title": fm.get("title", ""),
            "tags": [t.strip() for t in fm.get("tags", "").split(",") if t.strip()],
            "first_ts": fm.get("first_ts", ""),
            "last_ts": fm.get("last_ts", ""),
            "indexed_at": fm.get("indexed_at", ""),
            "source_path": fm.get("source_path", ""),
            "source_mtime_epoch": mtime_epoch,
            "source_size": size,
        }
    return pages


def read_wiki_meta(wiki_dir: Path) -> dict | None:
    meta_path = wiki_dir / "wiki-meta.json"
    if not meta_path.is_file():
        return None
    try:
        with open(meta_path, **FILE_ENCODING_KWARGS) as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def compute_staleness(last_refreshed_iso: str | None, staleness_hours, now=None):
    """Return (age_hours, stale) for a last_refreshed timestamp, or (None, None)
    if it can't be parsed. `now` is injectable for deterministic tests. Pure."""
    lr = parse_ts(last_refreshed_iso)
    if lr is None:
        return None, None
    if now is None:
        now = datetime.now(timezone.utc)
    age = (now - lr).total_seconds() / 3600.0
    try:
        threshold = float(staleness_hours)
    except (TypeError, ValueError):
        threshold = 6.0
    return round(age, 2), age > threshold


def compute_status(cfg: dict, wiki_dir_str: str | None, now=None) -> dict:
    """Build the status result dict. No printing; `now` injectable for tests."""
    result = {
        "config_default_wiki_dir": cfg.get("default_wiki_dir"),
        "staleness_hours": cfg.get("staleness_hours", 6),
        "wiki_dir": wiki_dir_str,
        "wiki_exists": False,
        "last_refreshed": None,
        "age_hours": None,
        "stale": None,
        "page_count": None,
    }
    if wiki_dir_str:
        wiki_dir = Path(wiki_dir_str).expanduser()
        meta = read_wiki_meta(wiki_dir)
        if meta:
            result["wiki_exists"] = True
            result["last_refreshed"] = meta.get("last_refreshed")
            result["page_count"] = meta.get("page_count")
            result["age_hours"], result["stale"] = compute_staleness(
                meta.get("last_refreshed"), result["staleness_hours"], now)
    return result


def status_command(args):
    cfg = load_config(args.config_file)
    wiki_dir_str = args.wiki_dir or cfg.get("default_wiki_dir")
    print(json.dumps(compute_status(cfg, wiki_dir_str), indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def parse_since(value: str):
    """Accept YYYY-MM-DD or a full ISO timestamp; return aware UTC datetime."""
    dt = parse_ts(value)
    if dt is None:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def resolve_from_time(all_: bool, since: str | None, meta: dict | None):
    """Resolve the plan's from-time. Returns (since_dt, source_label) or raises
    ValueError on an unparseable --since. Precedence: --all > --since > wiki
    last_refreshed > none. Pure."""
    if all_:
        return None, "--all (forced full scan)"
    if since:
        dt = parse_since(since)
        if dt is None:
            raise ValueError(f"could not parse --since {since!r} (use YYYY-MM-DD or ISO)")
        return dt, "--since argument"
    if meta and meta.get("last_refreshed"):
        return parse_ts(meta["last_refreshed"]), "wiki last_refreshed"
    return None, "none (all sessions)"


def classify_session_status(page: dict | None, machine: str, mtime_epoch: int, size: int) -> str:
    """new (no page) / unchanged (same machine + matching fingerprint) /
    changed (page exists but fingerprint or machine differs). Pure."""
    if page is None:
        return "new"
    if (page["machine"] == machine
            and page["source_mtime_epoch"] == mtime_epoch
            and page["source_size"] == size):
        return "unchanged"
    return "changed"


def build_plan(claude_dir: Path, wiki_dir: Path | None, since_dt, since_source: str,
               project_filters: list, last: int | None, machine: str | None = None) -> dict:
    """Enumerate sessions and classify them against the wiki. Returns the plan
    dict; no printing. `machine` injectable for deterministic tests."""
    if machine is None:
        machine = platform.node()
    pages = collect_wiki_pages(wiki_dir) if wiki_dir else {}
    meta = read_wiki_meta(wiki_dir) if wiki_dir else None

    sessions = []
    local_ids = set()
    for project_name, jsonl_path in find_session_files(claude_dir):
        if project_filters and not any(pf in project_name.lower() for pf in project_filters):
            continue
        mtime_epoch, size, subs = session_source_stat(jsonl_path)
        last_modified = datetime.fromtimestamp(mtime_epoch, tz=timezone.utc)
        session_id = jsonl_path.stem
        local_ids.add(session_id)
        if since_dt is not None and last_modified < since_dt:
            continue

        page = pages.get(session_id)
        sessions.append({
            "session_id": session_id,
            "project": project_name,
            "path": str(jsonl_path),
            "subagent_files": [str(s) for s in subs],
            "last_modified": last_modified.isoformat(timespec="seconds"),
            "source_mtime_epoch": mtime_epoch,
            "source_size": size,
            "status": classify_session_status(page, machine, mtime_epoch, size),
            "page": page["page"] if page else None,
        })

    sessions.sort(key=lambda s: s["source_mtime_epoch"], reverse=True)
    if last is not None:
        sessions = sessions[:last]

    wiki_only = [sid for sid in pages if sid not in local_ids]
    counts = defaultdict(int)
    for s in sessions:
        counts[s["status"]] += 1

    return {
        "generated_at": utc_now_iso(),
        "machine": machine,
        "claude_dir": str(claude_dir),
        "wiki_dir": str(wiki_dir) if wiki_dir else None,
        "wiki_last_refreshed": meta.get("last_refreshed") if meta else None,
        "from_time": since_dt.isoformat(timespec="seconds") if since_dt else None,
        "from_time_source": since_source,
        "counts": {"total": len(sessions), **counts},
        "wiki_only_sessions": len(wiki_only),
        "wiki_only_note": ("Pages exist in the wiki for sessions not found on this machine "
                           "(aged out or from another machine). NEVER delete them."),
        "sessions": sessions,
    }


def plan_command(args):
    claude_dir = Path(args.claude_dir).expanduser()
    cfg = load_config(args.config_file)
    wiki_dir_str = args.wiki_dir or cfg.get("default_wiki_dir")
    wiki_dir = Path(wiki_dir_str).expanduser() if wiki_dir_str else None
    meta = read_wiki_meta(wiki_dir) if wiki_dir else None

    try:
        since_dt, since_source = resolve_from_time(args.all, args.since, meta)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    project_filters = [p.lower() for p in (args.project or [])]
    plan = build_plan(claude_dir, wiki_dir, since_dt, since_source,
                      project_filters, args.last)
    print(json.dumps(plan, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# metrics / prompts / extract  (compute + rendering live in session_core;
# these wrappers just handle argv, file existence, and printing)
# ---------------------------------------------------------------------------

def metrics_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    metrics, warnings = compute_session_metrics(path)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    if warnings:
        print(f"# {len(warnings)} parse warning(s) (malformed lines skipped)", file=sys.stderr)


def prompts_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    records, warnings = read_jsonl_file(path)
    prompts = collect_prompts_from_records(records)
    print(render_prompts_markdown(prompts, args.max_chars))
    if warnings:
        print(f"# {len(warnings)} parse warning(s)", file=sys.stderr)


def extract_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    records, warnings = read_jsonl_file(path)
    subagent_files = session_source_stat(path)[2]
    print(render_extract(records, path.name, str(path), subagent_files,
                         max_text=args.max_text, max_tool=args.max_tool))
    if warnings:
        print(f"# {len(warnings)} warning(s) during parse:", file=sys.stderr)
        for w in warnings:
            print(f"#   {w}", file=sys.stderr)


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------

def order_pages(pages: dict) -> list:
    """Sort (session_id, page) pairs newest-first by last_ts. Pure."""
    return sorted(pages.items(), key=lambda kv: kv[1]["last_ts"] or "", reverse=True)


def render_index(ordered: list, started_at_iso: str) -> str:
    """Build INDEX.md text from ordered (session_id, page) pairs. Pure."""
    machines = sorted({p["machine"] for _, p in ordered if p["machine"]})
    lines = [
        "# Sessions Wiki Index",
        "",
        "<!-- Machine-generated by wiki_tools.py finalize. Do not hand-edit; edits are overwritten. -->",
        "",
        f"last_refreshed: {started_at_iso}",
        f"format_version: {FORMAT_VERSION}",
        f"session_count: {len(ordered)}",
        f"machines: {', '.join(machines) if machines else '(none recorded)'}",
        "",
        "Note: last_refreshed is the START time of the most recent refresh run. "
        "This index may list sessions no longer present locally (aged out, or "
        "indexed on another machine); their pages remain valid history.",
        "",
        "## Sessions (newest first by last activity)",
        "",
    ]
    for sid, p in ordered:
        tags = ", ".join(p["tags"]) if p["tags"] else "-"
        lines.append(f"- id={sid} | project={p['project']} | machine={p['machine']} | "
                     f"span={p['first_ts']}..{p['last_ts']} | title={p['title']} | "
                     f"tags={tags} | page={p['page']}")
    lines.append("")
    return "\n".join(lines)


def build_tag_map(ordered: list) -> dict:
    """tag (lowercased) -> list of (session_id, page). Pure."""
    tag_map = defaultdict(list)
    for sid, p in ordered:
        for tag in p["tags"]:
            tag_map[tag.lower()].append((sid, p))
    return tag_map


def render_tags(tag_map: dict, started_at_iso: str) -> str:
    """Build tags/TAGS.md text from a tag map. Pure."""
    tlines = [
        "# Tag cross-reference",
        "",
        "<!-- Machine-generated by wiki_tools.py finalize. Do not hand-edit. -->",
        "",
        f"last_refreshed: {started_at_iso}",
        f"tag_count: {len(tag_map)}",
        "",
    ]
    for tag in sorted(tag_map):
        tlines.append(f"## {tag}")
        tlines.append("")
        for sid, p in tag_map[tag]:
            tlines.append(f"- id={sid} | {p['title']} | page={p['page']}")
        tlines.append("")
    return "\n".join(tlines)


def finalize_command(args):
    wiki_dir = Path(args.wiki_dir).expanduser()
    if not wiki_dir.is_dir():
        print(f"ERROR: wiki dir not found: {wiki_dir}", file=sys.stderr)
        sys.exit(2)

    started_at = parse_ts(args.started_at)
    if started_at is None:
        print(f"ERROR: --started-at must be an ISO timestamp, got {args.started_at!r}", file=sys.stderr)
        sys.exit(2)
    started_at_iso = started_at.isoformat(timespec="seconds")

    pages = collect_wiki_pages(wiki_dir)
    ordered = order_pages(pages)
    tag_map = build_tag_map(ordered)

    with open(wiki_dir / "INDEX.md", "w", **FILE_ENCODING_KWARGS) as f:
        f.write(render_index(ordered, started_at_iso))

    tags_dir = wiki_dir / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)
    with open(tags_dir / "TAGS.md", "w", **FILE_ENCODING_KWARGS) as f:
        f.write(render_tags(tag_map, started_at_iso))

    # ---- wiki-meta.json ----
    meta = read_wiki_meta(wiki_dir) or {}
    meta.setdefault("created_at", utc_now_iso())
    meta["format_version"] = FORMAT_VERSION
    meta["last_refreshed"] = started_at_iso
    meta["last_refresh_machine"] = platform.node()
    meta["last_refresh_finished_at"] = utc_now_iso()
    meta["page_count"] = len(ordered)
    with open(wiki_dir / "wiki-meta.json", "w", **FILE_ENCODING_KWARGS) as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(json.dumps({
        "wiki_dir": str(wiki_dir),
        "last_refreshed": meta["last_refreshed"],
        "page_count": len(ordered),
        "tag_count": len(tag_map),
        "index": str(wiki_dir / "INDEX.md"),
        "tags": str(tags_dir / "TAGS.md"),
    }, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# help (detailed, example-driven -- beyond argparse's terse -h)
# ---------------------------------------------------------------------------

# Ordered so `help` with no topic reads top-to-bottom as a workflow:
# config -> status -> plan -> (metrics/prompts/extract per session) -> finalize.
HELP_TOPICS = {
    "config": """\
config get|set --key KEY [--value VALUE]

  Read or write shared sessions-wiki config at
  ~/.claude/sessions-wiki/config.json (override the path with the top-level
  --config-file flag). Keys:
    default_wiki_dir  - wiki folder used when a command omits --wiki-dir.
    staleness_hours   - how old a wiki may be before the search skills offer
                        to refresh it (default 6). This script only stores it.

  Parameters:
    action   Positional: 'get' or 'set'. Required.
    --key    Which config key to read/write. For 'get', omit to dump all keys.
    --value  New value (only for 'set'). Numbers auto-coerce to int/float;
             the literal 'null' (or empty) clears the key. Required for 'set'.

  Examples:
    wiki_tools.py config get
    wiki_tools.py config get --key default_wiki_dir
    wiki_tools.py config set --key default_wiki_dir --value "D:\\wikis\\sessions"
    wiki_tools.py config set --key staleness_hours --value 24
    wiki_tools.py config set --key default_wiki_dir --value null   # clear it
""",
    "status": """\
status [--wiki-dir DIR]

  Report a wiki's last_refreshed timestamp and whether it is stale relative to
  the configured staleness_hours. Emits JSON (wiki_exists, last_refreshed,
  age_hours, stale, page_count). The search skills call this before searching.

  Parameters:
    --wiki-dir  Wiki folder to inspect. Defaults to config default_wiki_dir.

  Examples:
    wiki_tools.py status
    wiki_tools.py status --wiki-dir ./my-wiki
""",
    "plan": """\
plan [--wiki-dir DIR] [--claude-dir DIR] [--since T | --all] [--last N] [--project SUB ...]

  Enumerate local session JSONL files (newest-modified first, subagent
  transcripts folded into each session's fingerprint) and classify each against
  the wiki as new / changed / unchanged. Emits a JSON work plan. This is the
  first step of a build/refresh: 'new' and 'changed' are the work items;
  'unchanged' are already fully indexed; wiki_only_sessions are pages with no
  local source (NEVER delete them).

  From-time precedence (which sessions are in scope):
    --all           beats everything: consider every session, ignore any cutoff.
    --since T       an explicit cutoff. T is YYYY-MM-DD or a full ISO timestamp.
    (neither)       fall back to the wiki's last_refreshed (incremental refresh);
                    if the wiki has none yet, consider all sessions.
  The chosen source is echoed back as from_time_source in the output.

  Parameters:
    --wiki-dir    Wiki folder to compare against. Defaults to default_wiki_dir.
    --claude-dir  Claude Code home holding projects/**/*.jsonl (default ~/.claude).
    --since T     From-time cutoff (YYYY-MM-DD or ISO). Ignored if --all is set.
    --all         Ignore the from-time; consider every session on disk.
    --last N      After sorting newest-first, keep only the N most recently
                  modified sessions. Combine with --all to mean literally
                  "the last N sessions regardless of date". Omit for no cap.
    --project SUB Only projects whose munged dir name contains SUB (case-
                  insensitive). Repeatable to include several projects.

  Examples:
    wiki_tools.py plan --wiki-dir ./wiki                 # incremental since last_refreshed
    wiki_tools.py plan --wiki-dir ./wiki --all           # every session
    wiki_tools.py plan --all --last 5                    # the 5 most recent sessions
    wiki_tools.py plan --since 2026-07-01                # since a date
    wiki_tools.py plan --all --project Daily --project claude-skills
""",
    "metrics": """\
metrics SESSION_FILE

  Emit pricing-free per-session metrics as JSON: token buckets per model (main
  and sidechain separately), user-prompt count, gap-rewrite events (in tokens),
  repeat reads, largest tool results, context growth, tool-use counts, flags,
  and the source fingerprint (machine + mtime + size). Paste this verbatim into
  a session page's '## Metrics' block; session-retro prices it later at current
  rates. No dollar figures are ever produced here.

  Parameters:
    SESSION_FILE  Positional: path to the session .jsonl file. Required.

  Examples:
    wiki_tools.py metrics ~/.claude/projects/c--myproj/<uuid>.jsonl
""",
    "prompts": """\
prompts SESSION_FILE [--max-chars N]

  Emit every human prompt of a session, verbatim, as Markdown (subagent task
  prompts and tool-result turns excluded). Paste into a page's '## Prompts'
  section unmodified.

  Parameters:
    SESSION_FILE  Positional: path to the session .jsonl file. Required.
    --max-chars N Truncate any single prompt longer than N chars, with an
                  explicit truncation marker (default 4000).

  Examples:
    wiki_tools.py prompts <session>.jsonl
    wiki_tools.py prompts <session>.jsonl --max-chars 8000
""",
    "extract": """\
extract SESSION_FILE [--max-text N] [--max-tool N]

  Print a condensed, cheap-to-read transcript of one session (deduped assistant
  turns, prompts, tool calls, tool-result previews, token usage per turn) for a
  model to read instead of the raw JSONL. Subagent transcripts are listed, not
  inlined -- extract them separately if needed.

  Parameters:
    SESSION_FILE  Positional: path to the session .jsonl file. Required.
    --max-text N  Max chars per assistant text block (default 800).
    --max-tool N  Max chars per tool input / tool-result preview (default 200).

  Examples:
    wiki_tools.py extract <session>.jsonl
    wiki_tools.py extract <session>.jsonl --max-text 2000 --max-tool 500
""",
    "finalize": """\
finalize --wiki-dir DIR --started-at ISO

  Regenerate INDEX.md and tags/TAGS.md from the session pages' frontmatter and
  stamp wiki-meta.json with last_refreshed. Run this once at the END of a
  build/refresh, after all session pages are written.

  Parameters:
    --wiki-dir DIR    Wiki folder to finalize. Required.
    --started-at ISO  ISO timestamp of when THIS refresh run STARTED (capture it
                      before step 1). It becomes last_refreshed, so sessions
                      modified mid-run get re-picked next time. Required.

  Examples:
    wiki_tools.py finalize --wiki-dir ./wiki --started-at 2026-07-12T09:00:00+00:00
""",
}

HELP_ORDER = ["config", "status", "plan", "metrics", "prompts", "extract", "finalize"]


def help_command(args):
    topic = getattr(args, "topic", None)
    if topic:
        key = topic.lstrip("-").lower()
        if key not in HELP_TOPICS:
            print(f"ERROR: no help for {topic!r}. Known commands: {', '.join(HELP_ORDER)}",
                  file=sys.stderr)
            sys.exit(2)
        print(f"wiki_tools.py {HELP_TOPICS[key].rstrip()}")
        return

    print("wiki_tools.py -- deterministic helper for the sessions-wiki skill family "
          "(pricing-free).")
    print("")
    print("Global option (before the subcommand):")
    print("  --config-file PATH  Override config path (default ~/.claude/sessions-wiki/config.json)")
    print("")
    print("Typical build/refresh order: config -> status -> plan -> "
          "metrics/prompts/extract (per session) -> finalize.")
    print("")
    print(f"Run 'wiki_tools.py help <command>' for one command. Commands: {', '.join(HELP_ORDER)}")
    print("")
    for key in HELP_ORDER:
        print("=" * 78)
        print(f"wiki_tools.py {HELP_TOPICS[key].rstrip()}")
        print("")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="wiki_tools.py",
        description="Deterministic helper for the sessions-wiki skill family (pricing-free).",
    )
    parser.add_argument("--config-file", help="Override the config path (default: ~/.claude/sessions-wiki/config.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    cfg_p = sub.add_parser("config", help="Get or set shared sessions-wiki config values")
    cfg_p.add_argument("action", choices=["get", "set"])
    cfg_p.add_argument("--key", help="Config key (default_wiki_dir, staleness_hours)")
    cfg_p.add_argument("--value", help="Value for 'set' (numbers auto-coerced; 'null' clears)")
    cfg_p.set_defaults(func=config_command)

    st_p = sub.add_parser("status", help="Report wiki last_refreshed + staleness vs configured staleness_hours")
    st_p.add_argument("--wiki-dir", help="Wiki directory (default: config default_wiki_dir)")
    st_p.set_defaults(func=status_command)

    plan_p = sub.add_parser("plan", help="Emit a JSON work plan of sessions to (re)index")
    plan_p.add_argument("--claude-dir", default="~/.claude", help="Claude Code home dir (default: ~/.claude)")
    plan_p.add_argument("--wiki-dir", help="Wiki directory (default: config default_wiki_dir)")
    plan_p.add_argument("--since", help="From-time: YYYY-MM-DD or ISO timestamp (default: wiki last_refreshed)")
    plan_p.add_argument("--all", action="store_true", help="Ignore from-time; consider every session")
    plan_p.add_argument("--last", type=int, help="Keep only the N most recently modified sessions")
    plan_p.add_argument("--project", action="append", help="Only projects whose dir name contains this substring (repeatable)")
    plan_p.set_defaults(func=plan_command)

    met_p = sub.add_parser("metrics", help="Emit pricing-free per-session metrics JSON")
    met_p.add_argument("session_file", help="Path to the session .jsonl file")
    met_p.set_defaults(func=metrics_command)

    pr_p = sub.add_parser("prompts", help="Emit all human prompts of a session, verbatim, as Markdown")
    pr_p.add_argument("session_file", help="Path to the session .jsonl file")
    pr_p.add_argument("--max-chars", type=int, default=4000, help="Max chars per prompt before truncation (default: 4000)")
    pr_p.set_defaults(func=prompts_command)

    ex_p = sub.add_parser("extract", help="Print a condensed transcript of one session (pricing-free)")
    ex_p.add_argument("session_file", help="Path to the session .jsonl file")
    ex_p.add_argument("--max-text", type=int, default=800, help="Max chars for assistant text (default: 800)")
    ex_p.add_argument("--max-tool", type=int, default=200, help="Max chars for tool inputs/results (default: 200)")
    ex_p.set_defaults(func=extract_command)

    fin_p = sub.add_parser("finalize", help="Regenerate INDEX.md + tags/TAGS.md and stamp last_refreshed")
    fin_p.add_argument("--wiki-dir", required=True, help="Wiki directory")
    fin_p.add_argument("--started-at", required=True, help="ISO timestamp of when this refresh run STARTED")
    fin_p.set_defaults(func=finalize_command)

    help_p = sub.add_parser("help", help="Detailed usage for all commands, or one: help plan")
    help_p.add_argument("topic", nargs="?", help="Command to explain (config, status, plan, metrics, prompts, extract, finalize). Omit for all.")
    help_p.set_defaults(func=help_command)

    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
