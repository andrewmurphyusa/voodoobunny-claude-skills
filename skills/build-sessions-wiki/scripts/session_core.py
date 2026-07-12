#!/usr/bin/env python3
"""
session_core.py -- shared, pricing-free core for the sessions-wiki skill family.

Owned by build-sessions-wiki; imported by build-sessions-wiki/scripts/wiki_tools.py
directly and by session-retro/scripts/parse_sessions.py via a sys.path shim. The
two skills are tightly coupled (session-retro reads the wiki's config, pages, and
metrics format at runtime), so the JSONL parsing / dedup / token-bucketing /
fingerprint / gap-detection logic lives here ONCE instead of being duplicated.

Everything here is pricing-free: it deals in token counts only. Dollar figures
are session-retro's job -- it applies its own current pricing table to the token
buckets this module produces.

The design separates I/O from computation so pieces are individually testable:
  read_jsonl_file / read_session_records   -> touch disk, return raw records
  metrics_from_records                     -> pure: records + fingerprint -> dict
  detect_gap_events / compute_flags / ...  -> pure sub-analyses over records

Python 3, standard library only.
"""

from __future__ import annotations

import json
import platform
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows console encoding guard (importers may rely on this being set)
# ---------------------------------------------------------------------------
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FILE_ENCODING_KWARGS = {"encoding": "utf-8", "errors": "replace"}

FORMAT_VERSION = 1

TOKEN_KEYS = (
    "input_tokens",
    "cache_read_tokens",
    "cache_write_5m_tokens",
    "cache_write_1h_tokens",
    "output_tokens",
)

# Analysis thresholds (token/count based -- pricing-free by design).
GAP_CREATION_TOKEN_THRESHOLD = 4096
GAP_THRESHOLD_1H_DOMINANT = 3600  # seconds
GAP_THRESHOLD_5M_DOMINANT = 300   # seconds
GAP_FLAG_CREATION_TOKENS = 50_000
LARGE_TOOL_RESULT_TOKENS = 10_000
LONG_CONTEXT_TOKENS = 150_000
MANY_TURNS_THRESHOLD = 150


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# JSONL reading (the only disk-touching primitives)
# ---------------------------------------------------------------------------

def iter_jsonl(path: Path, warnings: list):
    """Yield parsed JSON objects from a JSONL file. Malformed lines are recorded
    in `warnings` and skipped; an unreadable file is recorded and yields nothing."""
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


def read_jsonl_file(path: Path) -> tuple[list, list]:
    """Read one JSONL file into (records, warnings)."""
    warnings: list = []
    records = list(iter_jsonl(path, warnings))
    return records, warnings


def find_subagent_files(session_path: Path):
    """Subagent (sidechain) transcripts live in
    <project-dir>/<session-id>/subagents/agent-*.jsonl -- NOT inline. Missing
    them silently drops sidechain activity."""
    subagents_dir = session_path.parent / session_path.stem / "subagents"
    if not subagents_dir.is_dir():
        return []
    return sorted(subagents_dir.glob("*.jsonl"))


def read_session_records(path: Path) -> tuple[list, list, list]:
    """Read a session's main JSONL plus any subagent transcripts into one record
    list. Returns (records, warnings, subagent_files)."""
    warnings: list = []
    subs = find_subagent_files(path)
    records = []
    for src in [path] + subs:
        records.extend(iter_jsonl(src, warnings))
    return records, warnings, subs


def session_source_stat(session_path: Path) -> tuple[int, int, list]:
    """(max mtime epoch-seconds, total size bytes, subagent files) across the
    main JSONL and its subagent transcripts. This is the 'fully indexed'
    fingerprint stored on each wiki page and re-checked by session-retro."""
    subs = find_subagent_files(session_path)
    mtime = 0
    size = 0
    for f in [session_path] + subs:
        try:
            st = f.stat()
        except OSError:
            continue
        mtime = max(mtime, int(st.st_mtime))
        size += st.st_size
    return mtime, size, subs


def find_session_files(claude_dir: Path):
    """Yield (project_dir_name, jsonl_path) for every session under
    <claude_dir>/projects/*/*.jsonl."""
    projects_dir = claude_dir / "projects"
    if not projects_dir.is_dir():
        return
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl_path in sorted(project_dir.glob("*.jsonl")):
            yield project_dir.name, jsonl_path


# ---------------------------------------------------------------------------
# record-level pure helpers
# ---------------------------------------------------------------------------

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
    timestamp ascending. Duplicate assistant lines are a Claude Code
    streaming/retry artifact and roughly double apparent cost if not handled."""
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
    """Return (joined_text, tool_result_blocks) for a user message."""
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


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, {len(text)} chars total]"


# ---------------------------------------------------------------------------
# wiki page frontmatter + metrics-block reading (shared by both skills)
# ---------------------------------------------------------------------------

def parse_frontmatter(path: Path) -> dict | None:
    """Parse a flat 'key: value' frontmatter block delimited by --- lines.
    Returns None if the file has no (terminated) frontmatter."""
    try:
        with open(path, **FILE_ENCODING_KWARGS) as f:
            if f.readline().strip() != "---":
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


def read_page_metrics_block(page_path: Path, warnings: list) -> dict | None:
    """Extract and parse the fenced ```json block under the '## Metrics' heading
    of a wiki session page. Returns the parsed dict or None."""
    try:
        with open(page_path, **FILE_ENCODING_KWARGS) as f:
            text = f.read()
    except Exception as e:
        warnings.append(f"{page_path}: could not read wiki page ({e})")
        return None
    idx = text.find("## Metrics")
    if idx == -1:
        return None
    start = text.find("```json", idx)
    if start == -1:
        return None
    start = text.find("\n", start) + 1
    end = text.find("```", start)
    if end == -1:
        return None
    try:
        return json.loads(text[start:end])
    except Exception as e:
        warnings.append(f"{page_path}: malformed metrics JSON block ({e})")
        return None


# ---------------------------------------------------------------------------
# pure sub-analyses (individually testable)
# ---------------------------------------------------------------------------

def detect_gap_events(main_chain_requests: list, ttl_dominant: str) -> tuple[list, int]:
    """Find cache gap-rewrite events on the main chain. Each item of
    main_chain_requests is {"ts": datetime|None, "buckets": {...}, "model_key": str}.
    Returns (gap_events, gap_creation_tokens_total). Pricing-free: each event
    carries its cache-write token split and model_key so a caller can price it."""
    gap_threshold = GAP_THRESHOLD_1H_DOMINANT if ttl_dominant == "1h" else GAP_THRESHOLD_5M_DOMINANT
    gap_events = []
    total = 0
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
            total += creation_tokens
            gap_events.append({
                "timestamp": ts.isoformat(),
                "gap_seconds": round(gap_seconds, 1),
                "creation_tokens": creation_tokens,
                "cache_write_5m_tokens": b["cache_write_5m_tokens"],
                "cache_write_1h_tokens": b["cache_write_1h_tokens"],
                "model_key": item["model_key"],
            })
        prev_ts = ts
    return gap_events, total


def top_large_tool_results(user_records: list, tool_use_id_to_name: dict, limit: int = 5) -> list:
    """Top-N tool results by estimated token size across user records."""
    results = []
    for urec in user_records:
        msg = urec.get("message") or {}
        _, tool_result_blocks = extract_user_content_blocks(msg)
        for block in tool_result_blocks:
            try:
                est_tokens = len(json.dumps(block)) // 4
            except Exception:
                continue
            results.append({
                "tool_use_id": block.get("tool_use_id"),
                "tool_name": tool_use_id_to_name.get(block.get("tool_use_id"), "unknown"),
                "est_tokens": est_tokens,
            })
    results.sort(key=lambda x: x["est_tokens"], reverse=True)
    return results[:limit]


def count_user_prompts(user_records: list) -> int:
    """Count genuine human prompts: exclude isMeta, sidechain task prompts, and
    turns that are purely a tool_result being fed back."""
    count = 0
    for urec in user_records:
        if urec.get("isMeta") or urec.get("isSidechain"):
            continue
        msg = urec.get("message") or {}
        text, tool_result_blocks = extract_user_content_blocks(msg)
        if tool_result_blocks:
            continue
        if text and text.strip():
            count += 1
    return count


def context_growth(contexts: list) -> dict:
    """first / max / last context-token size across the main chain."""
    if not contexts:
        return {"first": 0, "max": 0, "last": 0}
    return {"first": contexts[0], "max": max(contexts), "last": contexts[-1]}


def compute_flags(*, gap_triggered: bool, read_file_counts: dict, large_tool_results: list,
                  context_last: int, total_requests: int, unknown_models) -> list:
    """Assemble the flag list. `gap_triggered` is decided by the caller so this
    works for both the pricing-free (token-threshold) and priced (dollar-
    threshold) definitions of GAP_REWRITES. `read_file_counts` may be the full
    per-file counts or just the >=2 subset (repeat_reads) -- both give the same
    result since the checks are >=2 and >=3."""
    flags = []
    if gap_triggered:
        flags.append("GAP_REWRITES")
    files_ge2 = [n for n in read_file_counts.values() if n >= 2]
    files_ge3 = [n for n in read_file_counts.values() if n >= 3]
    if files_ge3 or len(files_ge2) >= 5:
        flags.append("REPEAT_READS")
    if any((r.get("est_tokens", 0) or 0) >= LARGE_TOOL_RESULT_TOKENS for r in large_tool_results):
        flags.append("LARGE_TOOL_RESULTS")
    if context_last > LONG_CONTEXT_TOKENS:
        flags.append("LONG_CONTEXT")
    if total_requests > MANY_TURNS_THRESHOLD:
        flags.append("MANY_TURNS")
    if unknown_models:
        flags.append("UNKNOWN_MODEL")
    return flags


# ---------------------------------------------------------------------------
# metrics_from_records -- the pure pricing-free aggregation (Tier 1 seam)
# ---------------------------------------------------------------------------

def _new_model_bucket():
    return {"requests": 0, **{k: 0 for k in TOKEN_KEYS}}


def classify_records(records: list) -> dict:
    """Split a raw record list into the categories the metrics pass needs."""
    out = {"assistant": [], "user": [], "ai_titles": [], "summaries": []}
    for obj in records:
        rtype = obj.get("type")
        if rtype == "assistant":
            out["assistant"].append(obj)
        elif rtype == "user":
            out["user"].append(obj)
        elif rtype == "ai-title":
            t = obj.get("title") or obj.get("text") or obj.get("content")
            if isinstance(t, str) and t.strip():
                out["ai_titles"].append(t.strip())
        elif rtype == "summary":
            s = obj.get("summary")
            if isinstance(s, str) and s.strip():
                out["summaries"].append(s.strip())
    return out


def metrics_from_records(records: list, *, session_id: str, project: str, path: str,
                         source_mtime_epoch: int, source_size: int, subagent_files: list,
                         machine: str | None = None, generated_at: str | None = None,
                         warnings_count: int = 0) -> dict:
    """Pure: turn a session's raw record list + fingerprint into the pricing-free
    metrics dict. No disk access -- feed it in-memory records in tests. Returns a
    dict with "empty": True when the session has no billable assistant activity."""
    if machine is None:
        machine = platform.node()
    if generated_at is None:
        generated_at = utc_now_iso()

    cats = classify_records(records)
    assistant_records = dedupe_assistant_records(cats["assistant"])
    user_records = cats["user"]

    cwd = git_branch = cc_version = None
    tokens_totals = {k: 0 for k in TOKEN_KEYS}
    model_mix_main = defaultdict(_new_model_bucket)
    model_mix_sidechain = defaultdict(_new_model_bucket)
    unknown_models = set()

    main_chain_requests = []
    main_chain_contexts = []
    sidechain_requests = 0
    total_requests = 0

    tool_use_id_to_name = {}
    read_file_counts = defaultdict(int)
    tool_use_counts = defaultdict(int)

    first_ts = last_ts = None

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
        mm = (model_mix_sidechain if is_sidechain else model_mix_main)[model_key]
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
            "generated_at": generated_at,
            "session_id": session_id,
            "path": path,
            "empty": True,
            "warnings_count": warnings_count,
        }

    ttl_dominant = ("1h" if tokens_totals["cache_write_1h_tokens"] >= tokens_totals["cache_write_5m_tokens"]
                    else "5m")
    gap_events, gap_creation_tokens_total = detect_gap_events(main_chain_requests, ttl_dominant)
    large_tool_results = top_large_tool_results(user_records, tool_use_id_to_name)
    user_prompt_count = count_user_prompts(user_records)
    context = context_growth(main_chain_contexts)
    repeat_reads = {fp: n for fp, n in read_file_counts.items() if n >= 2}

    flags = compute_flags(
        gap_triggered=gap_creation_tokens_total > GAP_FLAG_CREATION_TOKENS,
        read_file_counts=read_file_counts,
        large_tool_results=large_tool_results,
        context_last=context["last"],
        total_requests=total_requests,
        unknown_models=unknown_models,
    )

    return {
        "wiki_tools_version": FORMAT_VERSION,
        "generated_at": generated_at,
        "machine": machine,
        "session_id": session_id,
        "project": project,
        "path": path,
        "subagent_files": [str(s) for s in subagent_files],
        "source_mtime_epoch": source_mtime_epoch,
        "source_size": source_size,
        "cwd": cwd,
        "git_branch": git_branch,
        "claude_code_version": cc_version,
        "ai_titles": cats["ai_titles"],
        "builtin_summaries": cats["summaries"],
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
        "context": context,
        "tool_use_counts": dict(sorted(tool_use_counts.items(), key=lambda kv: -kv[1])),
        "flags": flags,
        "warnings_count": warnings_count,
    }


def compute_session_metrics(path: Path, *, machine: str | None = None,
                            generated_at: str | None = None) -> tuple[dict, list]:
    """Disk wrapper around metrics_from_records: read the session (main + subagent
    files), stat the fingerprint, compute metrics. Returns (metrics, warnings)."""
    records, warnings, subs = read_session_records(path)
    mtime_epoch, size, _ = session_source_stat(path)
    metrics = metrics_from_records(
        records,
        session_id=path.stem,
        project=path.parent.name,
        path=str(path),
        source_mtime_epoch=mtime_epoch,
        source_size=size,
        subagent_files=subs,
        machine=machine,
        generated_at=generated_at,
        warnings_count=len(warnings),
    )
    return metrics, warnings


# ---------------------------------------------------------------------------
# transcript rendering (extract) and prompt collection -- pure over records
# ---------------------------------------------------------------------------

def collect_prompts_from_records(records: list) -> list:
    """Return [(timestamp, text)] for every genuine human prompt in a record
    list (main file only; excludes isMeta, sidechain, and tool-result turns)."""
    prompts = []
    for obj in records:
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
    return prompts


def render_prompts_markdown(prompts: list, max_chars: int = 4000) -> str:
    """Render collected prompts as the '## Prompts' Markdown section."""
    lines = [f"## Prompts (verbatim, {len(prompts)} total)", ""]
    for i, (ts, text) in enumerate(prompts, 1):
        lines.append(f"### Prompt {i} [{ts}]")
        lines.append("")
        lines.append(truncate(text, max_chars))
        lines.append("")
    return "\n".join(lines)


def render_extract(records: list, path_name: str, path_str: str, subagent_files: list,
                   max_text: int = 800, max_tool: int = 200, user_prompt_max: int = 1500,
                   usage_suffix=None) -> str:
    """Render a condensed, cheap-to-read transcript from a single session's record
    list (main file only). Pure -- no disk access.

    `usage_suffix`, if given, is called as usage_suffix(obj, usage) -> str and its
    return is appended after the token USAGE line (session-retro uses this to add
    per-request cost). When omitted, only a `[sidechain]` marker is appended."""
    # Which uuid is the retained "last occurrence" for each (message.id, requestId)?
    retained_uuid_by_key = {}
    for obj in records:
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message") or {}
        retained_uuid_by_key[(msg.get("id"), obj.get("requestId"))] = obj.get("uuid")

    lines = [f"# Condensed transcript: {path_name}", f"# session file: {path_str}"]
    if subagent_files:
        lines.append(f"# NOTE: this session has {len(subagent_files)} subagent transcript(s) not shown here."
                     " Extract them individually if needed:")
        for sf in subagent_files:
            lines.append(f"#   {sf}")
    lines.append("")

    for obj in records:
        rtype = obj.get("type")
        ts = obj.get("timestamp", "")

        if rtype == "user":
            if obj.get("isMeta"):
                continue
            msg = obj.get("message") or {}
            text, tool_result_blocks = extract_user_content_blocks(msg)
            if text and text.strip() and not tool_result_blocks:
                lines.append(f"[{ts}] USER: {truncate(text.strip(), user_prompt_max)}")
                lines.append("")
            for block in tool_result_blocks:
                content = block.get("content")
                preview = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                try:
                    est_tokens = len(json.dumps(block)) // 4
                except Exception:
                    est_tokens = 0
                err_flag = " ERROR" if block.get("is_error") else ""
                lines.append(f"  TOOL_RESULT [~{est_tokens} tok{err_flag}]: {truncate(preview or '', max_tool)}")
            continue

        if rtype != "assistant":
            continue

        msg = obj.get("message") or {}
        model = msg.get("model")
        if model == "<synthetic>":
            continue
        if retained_uuid_by_key.get((msg.get("id"), obj.get("requestId"))) != obj.get("uuid"):
            continue  # superseded duplicate

        content = msg.get("content") or []
        text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(t for t in text_parts if t)
        if text.strip():
            lines.append(f"[{ts}] ASSISTANT (model={model}): {truncate(text.strip(), max_text)}")

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            try:
                input_str = json.dumps(block.get("input", {}), ensure_ascii=False)
            except Exception:
                input_str = str(block.get("input"))
            lines.append(f"  TOOL_USE {block.get('name')}: {truncate(input_str, max_tool)}")

        usage = msg.get("usage")
        if usage:
            b = usage_token_buckets(usage)
            if usage_suffix is not None:
                suffix = usage_suffix(obj, usage)
            else:
                suffix = " [sidechain]" if obj.get("isSidechain") else ""
            lines.append(f"  USAGE: in={b['input_tokens']} cache_read={b['cache_read_tokens']} "
                         f"cache_write(5m={b['cache_write_5m_tokens']},1h={b['cache_write_1h_tokens']}) "
                         f"out={b['output_tokens']}{suffix}")
        lines.append("")

    return "\n".join(lines)
