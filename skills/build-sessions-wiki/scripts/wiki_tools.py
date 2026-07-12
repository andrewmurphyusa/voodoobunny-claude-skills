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
import os
import platform
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows console encoding guard
# ---------------------------------------------------------------------------
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FILE_ENCODING_KWARGS = {"encoding": "utf-8", "errors": "replace"}

FORMAT_VERSION = 1

# Analysis thresholds (token-based; mirrors session-retro's parse_sessions.py
# except that the gap-rewrite flag is expressed in tokens, not dollars,
# because this script is pricing-free).
GAP_CREATION_TOKEN_THRESHOLD = 4096
GAP_THRESHOLD_1H_DOMINANT = 3600  # seconds
GAP_THRESHOLD_5M_DOMINANT = 300   # seconds
GAP_FLAG_CREATION_TOKENS = 50_000
LARGE_TOOL_RESULT_TOKENS = 10_000
LONG_CONTEXT_TOKENS = 150_000
MANY_TURNS_THRESHOLD = 150

DEFAULT_CONFIG = {"default_wiki_dir": None, "staleness_hours": 6}

TOKEN_KEYS = (
    "input_tokens",
    "cache_read_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
    "output_tokens",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def iter_jsonl(path: Path, warnings: list):
    try:
        with open(path, **FILE_ENCODING_KWARGS) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception as e:
                    warnings.append(f"{path}:{lineno}: malformed JSON ({e})")
    except Exception as e:
        warnings.append(f"{path}: could not read file ({e})")


def resolve_model_key(model_name: str | None) -> tuple[str, bool]:
    """Substring-match a raw model string to a canonical key.
    Returns (key, is_unknown). Unknown models map to 'opus' and are flagged."""
    if not model_name:
        return "opus", True
    m = model_name.lower()
    if "fable" in m or "mythos" in m:
        return "fable", False
    if "opus" in m:
        return "opus", False
    if "sonnet" in m:
        return "sonnet5", False
    if "haiku" in m:
        return "haiku", False
    return "opus", True


def usage_token_buckets(usage: dict) -> dict:
    """Extract the five token buckets from a usage dict (pricing-free)."""
    cache_creation = usage.get("cache_creation") or {}
    w5 = cache_creation.get("ephemeral_5m_input_tokens", 0) or 0
    w1h = cache_creation.get("ephemeral_1h_input_tokens", 0) or 0
    total_creation = usage.get("cache_creation_input_tokens", 0) or 0
    # Verified corpora are 1h-TTL-dominant: if only the total is present,
    # attribute it to the 1h bucket rather than dropping it.
    if not cache_creation and total_creation:
        w1h = total_creation
    return {
        "input_tokens": usage.get("input_tokens", 0) or 0,
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0) or 0,
        "cache_write_5m_tokens": w5,
        "cache_write_1h_tokens": w1h,
        "output_tokens": usage.get("output_tokens", 0) or 0,
    }


def dedupe_assistant_records(raw_assistant_records: list) -> list:
    """Dedupe by (message.id, requestId), keep the LAST occurrence, sort by
    timestamp ascending. Same rule as session-retro's parser."""
    latest_by_key = {}
    fallback_seq = 0
    for rec in raw_assistant_records:
        msg = rec.get("message") or {}
        msg_id = msg.get("id")
        request_id = rec.get("requestId")
        if msg_id is None or request_id is None:
            fallback_seq += 1
            key = ("__no_id__", fallback_seq)
        else:
            key = (msg_id, request_id)
        latest_by_key[key] = rec
    records = list(latest_by_key.values())
    records.sort(key=lambda r: parse_ts(r.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
    return records


def extract_user_content_blocks(message: dict):
    content = message.get("content")
    if isinstance(content, str):
        return content, []
    if isinstance(content, list):
        text_parts = []
        tool_result_blocks = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_result":
                tool_result_blocks.append(block)
            elif btype == "text":
                text_parts.append(block.get("text", ""))
        return "\n".join(text_parts), tool_result_blocks
    return "", []


def find_subagent_files(session_path: Path):
    """Subagent (sidechain) transcripts live in
    <project-dir>/<session-id>/subagents/agent-*.jsonl -- NOT inline.
    Missing them silently drops sidechain activity."""
    subagents_dir = session_path.parent / session_path.stem / "subagents"
    if not subagents_dir.is_dir():
        return []
    return sorted(subagents_dir.glob("*.jsonl"))


def session_source_stat(session_path: Path) -> tuple[int, int, list]:
    """Combined (max mtime epoch-seconds, total size bytes, subagent files)
    across the main JSONL and any subagent transcripts. This pair is the
    'fully indexed' fingerprint stored in each wiki page."""
    subs = find_subagent_files(session_path)
    files = [session_path] + subs
    mtime = 0
    size = 0
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        mtime = max(mtime, int(st.st_mtime))
        size += st.st_size
    return mtime, size, subs


def find_session_files(claude_dir: Path):
    projects_dir = claude_dir / "projects"
    if not projects_dir.is_dir():
        return
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl_path in sorted(project_dir.glob("*.jsonl")):
            yield project_dir.name, jsonl_path


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, {len(text)} chars total]"


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
# wiki page frontmatter + meta
# ---------------------------------------------------------------------------

def parse_frontmatter(path: Path) -> dict | None:
    """Parse a flat 'key: value' frontmatter block delimited by --- lines.
    Returns None if the file has no frontmatter."""
    try:
        with open(path, **FILE_ENCODING_KWARGS) as f:
            first = f.readline()
            if first.strip() != "---":
                return None
            fm = {}
            for line in f:
                if line.strip() == "---":
                    return fm
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            return None  # unterminated frontmatter
    except Exception:
        return None


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
# metrics
# ---------------------------------------------------------------------------

def new_model_bucket():
    return {"requests": 0, **{k: 0 for k in TOKEN_KEYS}}


def compute_session_metrics(path: Path) -> tuple[dict, list]:
    """Parse one session (main + subagent files) into the pricing-free metrics
    dict. Returns (metrics, warnings); no printing. The empty-session case
    returns a dict with "empty": True. This is the function tests target."""
    warnings: list = []
    raw_assistant = []
    user_records = []
    ai_titles = []
    summaries = []

    files_to_read = [path] + find_subagent_files(path)
    for src in files_to_read:
        for obj in iter_jsonl(src, warnings):
            rtype = obj.get("type")
            if rtype == "assistant":
                raw_assistant.append(obj)
            elif rtype == "user":
                user_records.append(obj)
            elif rtype == "ai-title":
                t = obj.get("title") or obj.get("text") or obj.get("content")
                if isinstance(t, str) and t.strip():
                    ai_titles.append(t.strip())
            elif rtype == "summary":
                s = obj.get("summary")
                if isinstance(s, str) and s.strip():
                    summaries.append(s.strip())

    assistant_records = dedupe_assistant_records(raw_assistant)

    session_id = path.stem
    cwd = None
    git_branch = None
    cc_version = None

    tokens_totals = {k: 0 for k in TOKEN_KEYS}
    model_mix_main = defaultdict(new_model_bucket)
    model_mix_sidechain = defaultdict(new_model_bucket)
    unknown_models = set()

    main_chain_requests = []
    main_chain_contexts = []
    sidechain_requests = 0
    total_requests = 0

    tool_use_id_to_name = {}
    read_file_counts = defaultdict(int)
    tool_use_counts = defaultdict(int)

    first_ts = None
    last_ts = None

    for rec in assistant_records:
        msg = rec.get("message") or {}
        model = msg.get("model")
        if model == "<synthetic>":
            continue
        usage = msg.get("usage")
        if not usage:
            continue

        session_id = rec.get("sessionId") or session_id
        if not rec.get("isSidechain"):
            cwd = cwd or rec.get("cwd")
            git_branch = git_branch or rec.get("gitBranch")
            cc_version = cc_version or rec.get("version")

        ts = parse_ts(rec.get("timestamp"))
        if ts is not None:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

        model_key, is_unknown = resolve_model_key(model)
        if is_unknown:
            unknown_models.add(model or "<missing>")

        buckets = usage_token_buckets(usage)
        total_requests += 1
        for k in TOKEN_KEYS:
            tokens_totals[k] += buckets[k]

        is_sidechain = bool(rec.get("isSidechain"))
        mix = model_mix_sidechain if is_sidechain else model_mix_main
        mm = mix[model_key]
        mm["requests"] += 1
        for k in TOKEN_KEYS:
            mm[k] += buckets[k]

        if is_sidechain:
            sidechain_requests += 1
        else:
            context_tokens = (buckets["input_tokens"] + buckets["cache_read_tokens"]
                              + buckets["cache_write_5m_tokens"] + buckets["cache_write_1h_tokens"])
            main_chain_requests.append({"ts": ts, "buckets": buckets, "model_key": model_key})
            main_chain_contexts.append(context_tokens)

        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_use_id_to_name[block.get("id")] = block.get("name")
            tool_use_counts[block.get("name") or "unknown"] += 1
            if block.get("name") == "Read":
                fp = (block.get("input") or {}).get("file_path")
                if fp:
                    read_file_counts[fp] += 1

    if total_requests == 0:
        return {
            "wiki_tools_version": FORMAT_VERSION,
            "generated_at": utc_now_iso(),
            "session_id": session_id,
            "path": str(path),
            "empty": True,
            "warnings": warnings,
        }, warnings

    # --- Gap-rewrite detection (main chain only, TTL-aware, token-based) ---
    ttl_dominant = ("1h" if tokens_totals["cache_write_1h_tokens"] >= tokens_totals["cache_write_5m_tokens"]
                    else "5m")
    gap_threshold = GAP_THRESHOLD_1H_DOMINANT if ttl_dominant == "1h" else GAP_THRESHOLD_5M_DOMINANT

    gap_events = []
    gap_creation_tokens_total = 0
    prev_ts = None
    for i, item in enumerate(main_chain_requests):
        ts = item["ts"]
        b = item["buckets"]
        if i == 0 or ts is None or prev_ts is None:
            prev_ts = ts
            continue
        gap_seconds = (ts - prev_ts).total_seconds()
        creation_tokens = b["cache_write_5m_tokens"] + b["cache_write_1h_tokens"]
        if creation_tokens > GAP_CREATION_TOKEN_THRESHOLD and gap_seconds > gap_threshold:
            gap_creation_tokens_total += creation_tokens
            gap_events.append({
                "timestamp": ts.isoformat(),
                "gap_seconds": round(gap_seconds, 1),
                "creation_tokens": creation_tokens,
                "cache_write_5m_tokens": b["cache_write_5m_tokens"],
                "cache_write_1h_tokens": b["cache_write_1h_tokens"],
                "model_key": item["model_key"],
            })
        prev_ts = ts

    # --- Large tool results (top 5, estimated tokens) ---
    large_tool_results = []
    for urec in user_records:
        msg = urec.get("message") or {}
        _, tool_result_blocks = extract_user_content_blocks(msg)
        for block in tool_result_blocks:
            try:
                est_tokens = len(json.dumps(block)) // 4
            except Exception:
                continue
            tool_name = tool_use_id_to_name.get(block.get("tool_use_id"), "unknown")
            large_tool_results.append({
                "tool_use_id": block.get("tool_use_id"),
                "tool_name": tool_name,
                "est_tokens": est_tokens,
            })
    large_tool_results.sort(key=lambda x: x["est_tokens"], reverse=True)
    large_tool_results = large_tool_results[:5]

    # --- User prompt count (human prompts only) ---
    user_prompt_count = 0
    for urec in user_records:
        if urec.get("isMeta") or urec.get("isSidechain"):
            continue
        msg = urec.get("message") or {}
        text, tool_result_blocks = extract_user_content_blocks(msg)
        if tool_result_blocks:
            continue
        if text and text.strip():
            user_prompt_count += 1

    context_first = main_chain_contexts[0] if main_chain_contexts else 0
    context_max = max(main_chain_contexts) if main_chain_contexts else 0
    context_last = main_chain_contexts[-1] if main_chain_contexts else 0

    repeat_reads = {fp: n for fp, n in read_file_counts.items() if n >= 2}

    flags = []
    if gap_creation_tokens_total > GAP_FLAG_CREATION_TOKENS:
        flags.append("GAP_REWRITES")
    files_ge2 = [n for n in read_file_counts.values() if n >= 2]
    files_ge3 = [n for n in read_file_counts.values() if n >= 3]
    if files_ge3 or len(files_ge2) >= 5:
        flags.append("REPEAT_READS")
    if any(r["est_tokens"] >= LARGE_TOOL_RESULT_TOKENS for r in large_tool_results):
        flags.append("LARGE_TOOL_RESULTS")
    if context_last > LONG_CONTEXT_TOKENS:
        flags.append("LONG_CONTEXT")
    if total_requests > MANY_TURNS_THRESHOLD:
        flags.append("MANY_TURNS")
    if unknown_models:
        flags.append("UNKNOWN_MODEL")

    mtime_epoch, size, subs = session_source_stat(path)

    metrics = {
        "wiki_tools_version": FORMAT_VERSION,
        "generated_at": utc_now_iso(),
        "machine": platform.node(),
        "session_id": session_id,
        "project": path.parent.name,
        "path": str(path),
        "subagent_files": [str(s) for s in subs],
        "source_mtime_epoch": mtime_epoch,
        "source_size": size,
        "cwd": cwd,
        "git_branch": git_branch,
        "claude_code_version": cc_version,
        "ai_titles": ai_titles,
        "builtin_summaries": summaries,
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "requests": total_requests,
        "sidechain_requests": sidechain_requests,
        "user_prompts": user_prompt_count,
        "tokens": tokens_totals,
        "model_mix_main": {k: dict(v) for k, v in model_mix_main.items()},
        "model_mix_sidechain": {k: dict(v) for k, v in model_mix_sidechain.items()},
        "unknown_models": sorted(unknown_models),
        "ttl_dominant": ttl_dominant,
        "gap_events": gap_events,
        "gap_creation_tokens_total": gap_creation_tokens_total,
        "repeat_reads": repeat_reads,
        "large_tool_results": large_tool_results,
        "context": {"first": context_first, "max": context_max, "last": context_last},
        "tool_use_counts": dict(sorted(tool_use_counts.items(), key=lambda kv: -kv[1])),
        "flags": flags,
        "warnings_count": len(warnings),
    }
    return metrics, warnings


def metrics_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    metrics, warnings = compute_session_metrics(path)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    if warnings:
        print(f"# {len(warnings)} parse warning(s) (malformed lines skipped)", file=sys.stderr)


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------

def prompts_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    warnings: list = []
    prompts = []
    for obj in iter_jsonl(path, warnings):
        if obj.get("type") != "user":
            continue
        if obj.get("isMeta") or obj.get("isSidechain"):
            continue
        msg = obj.get("message") or {}
        text, tool_result_blocks = extract_user_content_blocks(msg)
        if tool_result_blocks:
            continue
        if text and text.strip():
            prompts.append((obj.get("timestamp", ""), text.strip()))

    print(f"## Prompts (verbatim, {len(prompts)} total)")
    print("")
    for i, (ts, text) in enumerate(prompts, 1):
        print(f"### Prompt {i} [{ts}]")
        print("")
        print(truncate(text, args.max_chars))
        print("")
    if warnings:
        print(f"# {len(warnings)} parse warning(s)", file=sys.stderr)


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def extract_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    warnings: list = []

    # First pass: for each (message.id, requestId), which uuid is retained.
    retained_uuid_by_key = {}
    for obj in iter_jsonl(path, warnings):
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message") or {}
        key = (msg.get("id"), obj.get("requestId"))
        retained_uuid_by_key[key] = obj.get("uuid")

    USER_PROMPT_MAX = 1500

    print(f"# Condensed transcript: {path.name}")
    print(f"# session file: {path}")
    subagent_files = find_subagent_files(path)
    if subagent_files:
        print(f"# NOTE: this session has {len(subagent_files)} subagent transcript(s) not shown here."
              " Extract them individually if needed:")
        for sf in subagent_files:
            print(f"#   {sf}")
    print("")

    for obj in iter_jsonl(path, warnings):
        rtype = obj.get("type")
        ts = obj.get("timestamp", "")

        if rtype == "user":
            if obj.get("isMeta"):
                continue
            msg = obj.get("message") or {}
            text, tool_result_blocks = extract_user_content_blocks(msg)
            if text and text.strip() and not tool_result_blocks:
                print(f"[{ts}] USER: {truncate(text.strip(), USER_PROMPT_MAX)}")
                print("")
            for block in tool_result_blocks:
                content = block.get("content")
                preview = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                try:
                    est_tokens = len(json.dumps(block)) // 4
                except Exception:
                    est_tokens = 0
                err_flag = " ERROR" if block.get("is_error") else ""
                print(f"  TOOL_RESULT [~{est_tokens} tok{err_flag}]: {truncate(preview or '', args.max_tool)}")
            continue

        if rtype != "assistant":
            continue

        msg = obj.get("message") or {}
        model = msg.get("model")
        if model == "<synthetic>":
            continue
        key = (msg.get("id"), obj.get("requestId"))
        if retained_uuid_by_key.get(key) != obj.get("uuid"):
            continue  # superseded duplicate

        content = msg.get("content") or []
        text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(t for t in text_parts if t)
        if text.strip():
            print(f"[{ts}] ASSISTANT (model={model}): {truncate(text.strip(), args.max_text)}")

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            try:
                input_str = json.dumps(block.get("input", {}), ensure_ascii=False)
            except Exception:
                input_str = str(block.get("input"))
            print(f"  TOOL_USE {block.get('name')}: {truncate(input_str, args.max_tool)}")

        usage = msg.get("usage")
        if usage:
            b = usage_token_buckets(usage)
            sidechain_flag = " [sidechain]" if obj.get("isSidechain") else ""
            print(f"  USAGE: in={b['input_tokens']} cache_read={b['cache_read_tokens']} "
                  f"cache_write(5m={b['cache_write_5m_tokens']},1h={b['cache_write_1h_tokens']}) "
                  f"out={b['output_tokens']}{sidechain_flag}")
        print("")

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
