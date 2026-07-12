#!/usr/bin/env python3
"""
parse_sessions.py -- deterministic parser for Claude Code session JSONL transcripts.

Part of the session-retro skill. "Scripts count, Fable judges": this script does
all aggregation/arithmetic; nothing here makes qualitative judgments.

Two subcommands:

  scan     Walk ~/.claude/projects/**/*.jsonl, compute per-session metrics
           (tokens, cost, gap-rewrite waste, re-reads, large tool results,
           context growth, flags), and write metrics.json + summary.md.

  extract  Produce a condensed, cheap-to-read transcript of a single session
           JSONL file to stdout, for Fable to read instead of raw JSONL.

Python 3, standard library only.
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
    # reconfigure() not available on very old Pythons / non-tty streams
    pass

FILE_ENCODING_KWARGS = {"encoding": "utf-8", "errors": "replace"}

# ---------------------------------------------------------------------------
# Pricing table (USD per million tokens). Cached 2026-07-07 -- if this script
# is used more than ~1 month after that date, re-verify rates (e.g. via the
# claude-api skill) before trusting cost output. See references/pricing.md.
# ---------------------------------------------------------------------------
DEFAULT_PRICING = {
    "fable": {"input": 10.0, "output": 50.0},
    "opus": {"input": 5.0, "output": 25.0},
    "sonnet5": {"input": 3.0, "output": 15.0},
    "sonnet5_intro": {"input": 2.0, "output": 10.0},  # through 2026-08-31
    "haiku": {"input": 1.0, "output": 5.0},
}

# Cache multipliers, relative to the model's *input* rate.
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_5M_MULTIPLIER = 1.25
CACHE_WRITE_1H_MULTIPLIER = 2.0

GAP_CREATION_TOKEN_THRESHOLD = 4096
GAP_THRESHOLD_1H_DOMINANT = 3600  # seconds
GAP_THRESHOLD_5M_DOMINANT = 300  # seconds

LARGE_TOOL_RESULT_TOKENS = 10_000
LONG_CONTEXT_TOKENS = 150_000
MANY_TURNS_THRESHOLD = 150
GAP_WASTE_FLAG_USD = 0.50


def load_pricing(pricing_file: str | None, sonnet5_intro: bool) -> dict:
    """Build the effective pricing table: defaults, overridden by --pricing-file,
    then adjusted for --sonnet5-intro."""
    pricing = {k: dict(v) for k, v in DEFAULT_PRICING.items()}
    if pricing_file:
        try:
            with open(pricing_file, **FILE_ENCODING_KWARGS) as f:
                overrides = json.load(f)
        except Exception as e:
            print(f"WARNING: could not load --pricing-file {pricing_file}: {e}", file=sys.stderr)
            overrides = {}
        for key, rates in overrides.items():
            pricing.setdefault(key, {})
            pricing[key].update(rates)

    effective_sonnet5 = dict(pricing["sonnet5_intro"] if sonnet5_intro else pricing["sonnet5"])
    pricing["sonnet5_effective"] = effective_sonnet5
    return pricing


def resolve_model_key(model_name: str | None) -> tuple[str, bool]:
    """Resolve a raw model string to a pricing key by substring match.

    Returns (key, is_unknown). key is one of: fable, opus, sonnet5, haiku.
    Unknown models are priced at opus rates and flagged.
    """
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


def rates_for(model_key: str, pricing: dict) -> tuple[float, float]:
    if model_key == "sonnet5":
        rates = pricing["sonnet5_effective"]
    else:
        rates = pricing[model_key]
    return rates["input"], rates["output"]


def compute_request_cost(usage: dict, model_key: str, pricing: dict) -> dict:
    """Given a usage dict and resolved model key, compute token counts and cost
    breakdown for a single request."""
    input_tokens = usage.get("input_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_creation = usage.get("cache_creation") or {}
    w5 = cache_creation.get("ephemeral_5m_input_tokens", 0) or 0
    w1h = cache_creation.get("ephemeral_1h_input_tokens", 0) or 0
    # Fallback: if the breakdown is missing but a total is present, and Claude
    # Code sessions verified so far are 1h-TTL-dominant, attribute the total
    # to the 1h bucket rather than silently dropping it.
    total_creation = usage.get("cache_creation_input_tokens", 0) or 0
    if not cache_creation and total_creation:
        w1h = total_creation
    output_tokens = usage.get("output_tokens", 0) or 0

    input_rate, output_rate = rates_for(model_key, pricing)

    cost_input = input_tokens * input_rate / 1e6
    cost_cache_read = cache_read * (CACHE_READ_MULTIPLIER * input_rate) / 1e6
    cost_cache_write_5m = w5 * (CACHE_WRITE_5M_MULTIPLIER * input_rate) / 1e6
    cost_cache_write_1h = w1h * (CACHE_WRITE_1H_MULTIPLIER * input_rate) / 1e6
    cost_output = output_tokens * output_rate / 1e6
    cost_total = cost_input + cost_cache_read + cost_cache_write_5m + cost_cache_write_1h + cost_output

    return {
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_5m_tokens": w5,
        "cache_write_1h_tokens": w1h,
        "output_tokens": output_tokens,
        "creation_tokens": w5 + w1h,
        "context_tokens": input_tokens + cache_read + w5 + w1h,
        "cost_input": cost_input,
        "cost_cache_read": cost_cache_read,
        "cost_cache_write_5m": cost_cache_write_5m,
        "cost_cache_write_1h": cost_cache_write_1h,
        "cost_output": cost_output,
        "cost_total": cost_total,
        "input_rate": input_rate,
    }


def parse_ts(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def iter_jsonl(path: Path, warnings: list):
    """Yield parsed JSON objects from a JSONL file, one per line. Malformed
    lines are recorded in `warnings` and skipped."""
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


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def dedupe_assistant_records(raw_assistant_records: list) -> list:
    """Dedupe assistant records by (message.id, requestId), keeping the LAST
    occurrence. Returns records sorted by timestamp ascending."""
    latest_by_key = {}
    fallback_seq = 0
    for rec in raw_assistant_records:
        msg = rec.get("message") or {}
        msg_id = msg.get("id")
        request_id = rec.get("requestId")
        if msg_id is None or request_id is None:
            # Can't form the dedupe key; treat as unique using a synthetic key
            fallback_seq += 1
            key = ("__no_id__", fallback_seq)
        else:
            key = (msg_id, request_id)
        latest_by_key[key] = rec  # last occurrence wins by definition of iteration order

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
    """Claude Code stores subagent (sidechain) transcripts in a sibling
    directory named after the session, not inline in the session's own
    JSONL: <session-id>/subagents/agent-*.jsonl. Those records carry the
    parent's sessionId and isSidechain=True. Without pulling these in,
    sidechain cost/requests silently read as zero and total cost badly
    undercounts (verified: ~870 requests / ~$33 missing across this corpus)."""
    subagents_dir = session_path.parent / session_path.stem / "subagents"
    if not subagents_dir.is_dir():
        return []
    return sorted(subagents_dir.glob("*.jsonl"))


def process_session_file(path: Path, project: str, args, pricing: dict, warnings: list):
    raw_assistant = []
    user_records = []
    all_records = []  # for since-filter we need timestamps across the file

    files_to_read = [path] + find_subagent_files(path)
    for src in files_to_read:
        for obj in iter_jsonl(src, warnings):
            rtype = obj.get("type")
            if rtype == "assistant":
                raw_assistant.append(obj)
                all_records.append(obj)
            elif rtype == "user":
                user_records.append(obj)
                all_records.append(obj)

    if not raw_assistant:
        return "empty"  # nothing to cost out; skip (e.g. empty/aborted session)

    # --since filtering, at session granularity: use the session's last
    # timestamp seen among assistant/user records.
    if args.since_dt is not None:
        last_ts = None
        for r in all_records:
            t = parse_ts(r.get("timestamp"))
            if t is not None and (last_ts is None or t > last_ts):
                last_ts = t
        if last_ts is not None and last_ts < args.since_dt:
            return "before_since"

    assistant_records = dedupe_assistant_records(raw_assistant)

    session_id = None
    tokens_totals = defaultdict(int)
    cost_totals = defaultdict(float)
    model_mix = defaultdict(lambda: {"requests": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0})
    unknown_models = set()

    main_chain_contexts = []  # ordered (timestamp, context_tokens) for non-sidechain
    main_chain_requests = []  # ordered non-sidechain request dicts w/ computed cost
    sidechain_requests = 0
    sidechain_cost = 0.0
    total_requests = 0

    tool_use_id_to_name = {}
    read_file_counts = defaultdict(int)

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

        session_id = rec.get("sessionId", session_id)
        ts = parse_ts(rec.get("timestamp"))
        if ts is not None:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

        model_key, is_unknown = resolve_model_key(model)
        if is_unknown:
            unknown_models.add(model or "<missing>")

        costed = compute_request_cost(usage, model_key, pricing)
        total_requests += 1

        for tok_key in ("input_tokens", "cache_read_tokens", "cache_write_5m_tokens",
                        "cache_write_1h_tokens", "output_tokens"):
            tokens_totals[tok_key] += costed[tok_key]
        for cost_key in ("cost_input", "cost_cache_read", "cost_cache_write_5m",
                         "cost_cache_write_1h", "cost_output", "cost_total"):
            cost_totals[cost_key] += costed[cost_key]

        mm = model_mix[model_key]
        mm["requests"] += 1
        mm["cost"] += costed["cost_total"]
        mm["input_tokens"] += costed["input_tokens"]
        mm["output_tokens"] += costed["output_tokens"]

        is_sidechain = bool(rec.get("isSidechain"))
        if is_sidechain:
            sidechain_requests += 1
            sidechain_cost += costed["cost_total"]
        else:
            main_chain_requests.append({"rec": rec, "costed": costed, "ts": ts})
            main_chain_contexts.append(costed["context_tokens"])

        # tool_use blocks -> re-read tracking + tool_use_id -> name map
        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_use_id_to_name[block.get("id")] = block.get("name")
            if block.get("name") == "Read":
                fp = (block.get("input") or {}).get("file_path")
                if fp:
                    read_file_counts[fp] += 1

    if total_requests == 0:
        return "empty"

    # --- Gap-rewrite detection (main chain only, TTL-aware per session) ---
    total_w5 = tokens_totals["cache_write_5m_tokens"]
    total_w1h = tokens_totals["cache_write_1h_tokens"]
    ttl_dominant = "1h" if total_w1h >= total_w5 else "5m"
    gap_threshold = GAP_THRESHOLD_1H_DOMINANT if ttl_dominant == "1h" else GAP_THRESHOLD_5M_DOMINANT

    gap_events = []
    wasted_usd_total = 0.0
    prev_ts = None
    for i, item in enumerate(main_chain_requests):
        ts = item["ts"]
        costed = item["costed"]
        if i == 0 or ts is None or prev_ts is None:
            prev_ts = ts
            continue
        gap_seconds = (ts - prev_ts).total_seconds()
        creation_tokens = costed["creation_tokens"]
        if creation_tokens > GAP_CREATION_TOKEN_THRESHOLD and gap_seconds > gap_threshold:
            w5 = costed["cache_write_5m_tokens"]
            w1h = costed["cache_write_1h_tokens"]
            input_rate = costed["input_rate"]
            wasted_usd = (
                w5 * (CACHE_WRITE_5M_MULTIPLIER - CACHE_READ_MULTIPLIER)
                + w1h * (CACHE_WRITE_1H_MULTIPLIER - CACHE_READ_MULTIPLIER)
            ) * input_rate / 1e6
            wasted_usd_total += wasted_usd
            gap_events.append({
                "timestamp": ts.isoformat(),
                "gap_seconds": gap_seconds,
                "creation_tokens": creation_tokens,
                "wasted_usd": round(wasted_usd, 4),
            })
        prev_ts = ts

    # --- Large tool results (top 5) ---
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
            content = block.get("content")
            preview = content if isinstance(content, str) else json.dumps(content)
            preview = (preview or "")[:200]
            large_tool_results.append({
                "tool_use_id": block.get("tool_use_id"),
                "tool_name": tool_name,
                "est_tokens": est_tokens,
                "preview": preview,
            })
    large_tool_results.sort(key=lambda x: x["est_tokens"], reverse=True)
    large_tool_results = large_tool_results[:5]

    # --- User prompt count ---
    user_prompt_count = 0
    for urec in user_records:
        if urec.get("isMeta") or urec.get("isSidechain"):
            continue  # exclude subagent task prompts -- not human-authored
        msg = urec.get("message") or {}
        text, tool_result_blocks = extract_user_content_blocks(msg)
        if tool_result_blocks:
            continue
        if text and text.strip():
            user_prompt_count += 1

    # --- Context growth ---
    context_first = main_chain_contexts[0] if main_chain_contexts else 0
    context_max = max(main_chain_contexts) if main_chain_contexts else 0
    context_last = main_chain_contexts[-1] if main_chain_contexts else 0

    # --- Repeat reads ---
    repeat_reads = {fp: n for fp, n in read_file_counts.items() if n >= 2}

    # --- Flags ---
    flags = []
    if wasted_usd_total > GAP_WASTE_FLAG_USD:
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

    return {
        "session_id": session_id or path.stem,
        "project": project,
        "path": str(path),
        "first_ts": first_ts.isoformat() if first_ts else None,
        "last_ts": last_ts.isoformat() if last_ts else None,
        "requests": total_requests,
        "sidechain_requests": sidechain_requests,
        "sidechain_cost": round(sidechain_cost, 4),
        "user_prompts": user_prompt_count,
        "tokens": dict(tokens_totals),
        "cost": {k: round(v, 4) for k, v in cost_totals.items()},
        "cost_total": round(cost_totals["cost_total"], 4),
        "model_mix": {k: {**v, "cost": round(v["cost"], 4)} for k, v in model_mix.items()},
        "unknown_models": sorted(unknown_models),
        "ttl_dominant": ttl_dominant,
        "gap_events": gap_events,
        "wasted_usd": round(wasted_usd_total, 4),
        "repeat_reads": repeat_reads,
        "large_tool_results": large_tool_results,
        "context": {"first": context_first, "max": context_max, "last": context_last},
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# sessions-wiki integration
#
# The build-sessions-wiki skill maintains an LLM-wiki with one page per session.
# Each page stores a "fully indexed" fingerprint (machine + source_mtime_epoch +
# source_size across main JSONL + subagent transcripts) and a machine-generated,
# PRICING-FREE metrics JSON block (token buckets per model, gap events in
# tokens). When a session's fingerprint still matches the live files, scan can
# build its record from the wiki page instead of re-parsing the JSONL, applying
# THIS script's current pricing table to the stored token counts. Dollar
# figures therefore never come from the wiki -- only tokens do.
# ---------------------------------------------------------------------------

def resolve_wiki_dir(args) -> Path | None:
    """--no-wiki disables; --wiki-dir wins; else fall back to default_wiki_dir
    in <claude-dir>/sessions-wiki/config.json (shared sessions-wiki config)."""
    if getattr(args, "no_wiki", False):
        return None
    if getattr(args, "wiki_dir", None):
        return Path(args.wiki_dir).expanduser()
    config_path = Path(args.claude_dir).expanduser() / "sessions-wiki" / "config.json"
    if config_path.is_file():
        try:
            with open(config_path, **FILE_ENCODING_KWARGS) as f:
                cfg = json.load(f)
            d = cfg.get("default_wiki_dir")
            if d:
                return Path(d).expanduser()
        except Exception as e:
            print(f"WARNING: could not read {config_path}: {e}", file=sys.stderr)
    return None


def parse_page_frontmatter(path: Path) -> dict | None:
    """Parse the wiki page's flat 'key: value' frontmatter (--- delimited)."""
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
    except Exception:
        pass
    return None


def collect_wiki_fingerprints(wiki_dir: Path, warnings: list) -> dict:
    """Map session_id -> fingerprint info for every sessions/**/*.md page."""
    pages = {}
    sessions_dir = wiki_dir / "sessions"
    if not sessions_dir.is_dir():
        warnings.append(f"wiki dir {wiki_dir} has no sessions/ subdir; ignoring wiki")
        return pages
    for md in sorted(sessions_dir.rglob("*.md")):
        fm = parse_page_frontmatter(md)
        if not fm or "session_id" not in fm:
            continue
        try:
            mtime_epoch = int(fm.get("source_mtime_epoch", "-1"))
            size = int(fm.get("source_size", "-1"))
        except ValueError:
            continue
        pages[fm["session_id"]] = {
            "abs_page": md,
            "page": str(md.relative_to(wiki_dir)).replace("\\", "/"),
            "machine": fm.get("machine", ""),
            "source_mtime_epoch": mtime_epoch,
            "source_size": size,
        }
    return pages


def session_source_stat(session_path: Path) -> tuple[int, int]:
    """(max mtime epoch-seconds, total size) across main + subagent files --
    must mirror wiki_tools.py's fingerprint computation exactly."""
    mtime = 0
    size = 0
    for f in [session_path] + find_subagent_files(session_path):
        try:
            st = f.stat()
        except OSError:
            continue
        mtime = max(mtime, int(st.st_mtime))
        size += st.st_size
    return mtime, size


def read_page_metrics_block(page_path: Path, warnings: list) -> dict | None:
    """Extract the fenced json block under the '## Metrics' heading."""
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


def safe_rates(model_key: str, pricing: dict) -> tuple[float, float]:
    try:
        return rates_for(model_key, pricing)
    except Exception:
        return rates_for("opus", pricing)


def session_record_from_wiki(wm: dict, project: str, jsonl_path: Path,
                             page_rel: str, pricing: dict, args):
    """Convert a wiki page's pricing-free metrics JSON into a session record
    shaped exactly like process_session_file's output, pricing the stored
    token buckets with the CURRENT pricing table. Returns the record dict,
    "empty", "before_since", or None if the metrics are unusable."""
    if not isinstance(wm, dict) or wm.get("empty"):
        return "empty" if isinstance(wm, dict) and wm.get("empty") else None
    if not wm.get("model_mix_main") and not wm.get("model_mix_sidechain"):
        return None

    if args.since_dt is not None:
        last = parse_ts(wm.get("last_ts"))
        if last is not None and last < args.since_dt:
            return "before_since"

    cost_totals = defaultdict(float)
    model_mix = defaultdict(lambda: {"requests": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0})
    sidechain_cost = 0.0

    for mix_name in ("model_mix_main", "model_mix_sidechain"):
        for mk, b in (wm.get(mix_name) or {}).items():
            if not isinstance(b, dict):
                return None
            input_rate, output_rate = safe_rates(mk, pricing)
            ci = (b.get("input_tokens", 0) or 0) * input_rate / 1e6
            ccr = (b.get("cache_read_tokens", 0) or 0) * CACHE_READ_MULTIPLIER * input_rate / 1e6
            c5 = (b.get("cache_write_5m_tokens", 0) or 0) * CACHE_WRITE_5M_MULTIPLIER * input_rate / 1e6
            c1 = (b.get("cache_write_1h_tokens", 0) or 0) * CACHE_WRITE_1H_MULTIPLIER * input_rate / 1e6
            co = (b.get("output_tokens", 0) or 0) * output_rate / 1e6
            total = ci + ccr + c5 + c1 + co
            cost_totals["cost_input"] += ci
            cost_totals["cost_cache_read"] += ccr
            cost_totals["cost_cache_write_5m"] += c5
            cost_totals["cost_cache_write_1h"] += c1
            cost_totals["cost_output"] += co
            cost_totals["cost_total"] += total
            mm = model_mix[mk]
            mm["requests"] += b.get("requests", 0) or 0
            mm["cost"] += total
            mm["input_tokens"] += b.get("input_tokens", 0) or 0
            mm["output_tokens"] += b.get("output_tokens", 0) or 0
            if mix_name == "model_mix_sidechain":
                sidechain_cost += total

    # Gap events: wiki stores tokens + model_key per event; price them now
    # (same formula as the live path -- see references/pricing.md).
    gap_events = []
    wasted_usd_total = 0.0
    for ev in wm.get("gap_events") or []:
        input_rate, _ = safe_rates(ev.get("model_key", "opus"), pricing)
        w5 = ev.get("cache_write_5m_tokens", 0) or 0
        w1h = ev.get("cache_write_1h_tokens", 0) or 0
        wasted_usd = (
            w5 * (CACHE_WRITE_5M_MULTIPLIER - CACHE_READ_MULTIPLIER)
            + w1h * (CACHE_WRITE_1H_MULTIPLIER - CACHE_READ_MULTIPLIER)
        ) * input_rate / 1e6
        wasted_usd_total += wasted_usd
        gap_events.append({
            "timestamp": ev.get("timestamp"),
            "gap_seconds": ev.get("gap_seconds"),
            "creation_tokens": ev.get("creation_tokens", 0),
            "wasted_usd": round(wasted_usd, 4),
        })

    tokens = {k: (wm.get("tokens") or {}).get(k, 0) or 0
              for k in ("input_tokens", "cache_read_tokens", "cache_write_5m_tokens",
                        "cache_write_1h_tokens", "output_tokens")}
    repeat_reads = wm.get("repeat_reads") or {}
    large_tool_results = wm.get("large_tool_results") or []
    context = wm.get("context") or {"first": 0, "max": 0, "last": 0}
    unknown_models = wm.get("unknown_models") or []
    total_requests = wm.get("requests", 0) or 0

    # Recompute flags with THIS skill's thresholds (dollar-based where the
    # original is dollar-based) -- never copy the wiki's token-based flags.
    flags = []
    if wasted_usd_total > GAP_WASTE_FLAG_USD:
        flags.append("GAP_REWRITES")
    files_ge2 = [n for n in repeat_reads.values() if n >= 2]
    files_ge3 = [n for n in repeat_reads.values() if n >= 3]
    if files_ge3 or len(files_ge2) >= 5:
        flags.append("REPEAT_READS")
    if any((r.get("est_tokens", 0) or 0) >= LARGE_TOOL_RESULT_TOKENS for r in large_tool_results):
        flags.append("LARGE_TOOL_RESULTS")
    if (context.get("last", 0) or 0) > LONG_CONTEXT_TOKENS:
        flags.append("LONG_CONTEXT")
    if total_requests > MANY_TURNS_THRESHOLD:
        flags.append("MANY_TURNS")
    if unknown_models:
        flags.append("UNKNOWN_MODEL")

    return {
        "session_id": wm.get("session_id") or jsonl_path.stem,
        "project": project,
        "path": str(jsonl_path),
        "first_ts": wm.get("first_ts"),
        "last_ts": wm.get("last_ts"),
        "requests": total_requests,
        "sidechain_requests": wm.get("sidechain_requests", 0) or 0,
        "sidechain_cost": round(sidechain_cost, 4),
        "user_prompts": wm.get("user_prompts", 0) or 0,
        "tokens": tokens,
        "cost": {k: round(v, 4) for k, v in cost_totals.items()},
        "cost_total": round(cost_totals["cost_total"], 4),
        "model_mix": {k: {**v, "cost": round(v["cost"], 4)} for k, v in model_mix.items()},
        "unknown_models": sorted(unknown_models),
        "ttl_dominant": wm.get("ttl_dominant", "1h"),
        "gap_events": gap_events,
        "wasted_usd": round(wasted_usd_total, 4),
        "repeat_reads": repeat_reads,
        "large_tool_results": large_tool_results,
        "context": context,
        "flags": flags,
        "source": "wiki",
        "wiki_page": page_rel,
    }


def find_session_files(claude_dir: Path):
    projects_dir = claude_dir / "projects"
    if not projects_dir.is_dir():
        return
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl_path in sorted(project_dir.glob("*.jsonl")):
            yield project_dir.name, jsonl_path


def scan_command(args):
    claude_dir = Path(args.claude_dir).expanduser()
    pricing = load_pricing(args.pricing_file, args.sonnet5_intro)

    since_dt = None
    if args.since:
        try:
            since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            print(f"ERROR: --since must be YYYY-MM-DD, got {args.since!r}", file=sys.stderr)
            sys.exit(2)
    args.since_dt = since_dt

    project_filters = [p.lower() for p in (args.project or [])]

    warnings = []
    sessions = []
    skipped_empty = 0
    skipped_since = 0
    files_seen = 0

    wiki_dir = resolve_wiki_dir(args)
    wiki_pages = collect_wiki_fingerprints(wiki_dir, warnings) if wiki_dir else {}
    this_machine = platform.node()

    for project_name, jsonl_path in find_session_files(claude_dir):
        if project_filters and not any(pf in project_name.lower() for pf in project_filters):
            continue
        files_seen += 1

        # Fully-indexed wiki page (same machine, matching mtime+size fingerprint
        # across main + subagent files) -> build the record from the wiki's
        # pricing-free metrics instead of re-parsing the JSONL.
        result = None
        fp = wiki_pages.get(jsonl_path.stem)
        if fp is not None and fp["machine"] == this_machine:
            mtime_epoch, size = session_source_stat(jsonl_path)
            if fp["source_mtime_epoch"] == mtime_epoch and fp["source_size"] == size:
                wm = read_page_metrics_block(fp["abs_page"], warnings)
                if wm is not None:
                    result = session_record_from_wiki(wm, project_name, jsonl_path,
                                                      fp["page"], pricing, args)
                if result is None:
                    warnings.append(f"{fp['abs_page']}: fingerprint matched but metrics "
                                    "block unusable; parsed JSONL instead")

        if result is None:
            result = process_session_file(jsonl_path, project_name, args, pricing, warnings)
            if isinstance(result, dict):
                result["source"] = "jsonl"

        if result == "empty":
            skipped_empty += 1
            continue
        if result == "before_since":
            skipped_since += 1
            continue
        sessions.append(result)

    sessions.sort(key=lambda s: s["cost_total"], reverse=True)

    # --- Aggregate totals ---
    totals = defaultdict(float)
    tokens_totals = defaultdict(int)
    model_mix_totals = defaultdict(lambda: {"requests": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0})
    projects = defaultdict(lambda: {"sessions": 0, "requests": 0, "cost_total": 0.0, "wasted_usd": 0.0})
    wasted_total = 0.0
    sidechain_cost_total = 0.0
    sidechain_requests_total = 0
    requests_total = 0

    for s in sessions:
        totals["cost_total"] += s["cost_total"]
        for k, v in s["cost"].items():
            if k != "cost_total":
                totals[k] += v
        for k, v in s["tokens"].items():
            tokens_totals[k] += v
        for mk, mv in s["model_mix"].items():
            mm = model_mix_totals[mk]
            mm["requests"] += mv["requests"]
            mm["cost"] += mv["cost"]
            mm["input_tokens"] += mv["input_tokens"]
            mm["output_tokens"] += mv["output_tokens"]
        wasted_total += s["wasted_usd"]
        sidechain_cost_total += s["sidechain_cost"]
        sidechain_requests_total += s["sidechain_requests"]
        requests_total += s["requests"]

        p = projects[s["project"]]
        p["sessions"] += 1
        p["requests"] += s["requests"]
        p["cost_total"] += s["cost_total"]
        p["wasted_usd"] += s["wasted_usd"]

    # --- Output dir ---
    if args.out:
        out_dir = Path(args.out).expanduser()
    else:
        run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = claude_dir / "session-retro" / "runs" / run_stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    sessions_from_wiki = sum(1 for s in sessions if s.get("source") == "wiki")

    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claude_dir": str(claude_dir),
        "filters": {"project": args.project, "since": args.since},
        "pricing": pricing,
        "wiki_dir": str(wiki_dir) if wiki_dir else None,
        "sessions_from_wiki": sessions_from_wiki,
        "sessions_from_jsonl": len(sessions) - sessions_from_wiki,
        "files_seen": files_seen,
        "sessions_included": len(sessions),
        "sessions_skipped_empty": skipped_empty,
        "sessions_skipped_before_since": skipped_since,
        "warnings": warnings,
        "totals": {
            "cost_total": round(totals["cost_total"], 4),
            "cost_breakdown": {k: round(v, 4) for k, v in totals.items() if k != "cost_total"},
            "tokens": dict(tokens_totals),
            "requests": requests_total,
            "sessions": len(sessions),
            "wasted_usd": round(wasted_total, 4),
            "sidechain_requests": sidechain_requests_total,
            "sidechain_cost": round(sidechain_cost_total, 4),
        },
        "model_mix": {k: {**v, "cost": round(v["cost"], 4)} for k, v in model_mix_totals.items()},
        "projects": {k: {**v, "cost_total": round(v["cost_total"], 4), "wasted_usd": round(v["wasted_usd"], 4)}
                     for k, v in projects.items()},
        "sessions": sessions,
    }

    metrics_path = out_dir / "metrics.json"
    with open(metrics_path, "w", **FILE_ENCODING_KWARGS) as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    summary_path = out_dir / "summary.md"
    write_summary(summary_path, metrics, args)

    print(f"Scanned {files_seen} session file(s); {len(sessions)} included, {skipped_empty} skipped (empty), "
          f"{skipped_since} skipped (before --since).")
    if warnings:
        print(f"{len(warnings)} warning(s) -- see metrics.json['warnings'].", file=sys.stderr)
    print(f"Total counterfactual API cost: ${metrics['totals']['cost_total']:.2f}")
    print(f"Output written to: {out_dir}")


def write_summary(path: Path, metrics: dict, args):
    lines = []
    lines.append("# session-retro scan summary")
    lines.append("")
    lines.append(f"Generated: {metrics['generated_at']}")
    lines.append(f"Claude dir: `{metrics['claude_dir']}`")
    filt = metrics["filters"]
    if filt["project"] or filt["since"]:
        lines.append(f"Filters: project={filt['project'] or 'ALL'}, since={filt['since'] or 'ALL'}")
    lines.append("")
    lines.append(
        "> Costs are **counterfactual API-equivalent pricing**, not real spend "
        "(this account is on a flat-rate plan). Pricing basis: "
        f"Sonnet 5 {'intro $2/$10' if args.sonnet5_intro else 'standard $3/$15'} "
        "per MTok in/out; see references/pricing.md. Cached 2026-07-07 -- verify if stale."
    )
    lines.append("")

    t = metrics["totals"]
    lines.append("## Overall totals")
    lines.append("")
    lines.append(
        f"- Sessions included: {t['sessions']} (skipped empty: {metrics['sessions_skipped_empty']}, "
        f"skipped before --since: {metrics['sessions_skipped_before_since']})"
    )
    lines.append(f"- Requests (deduped, non-synthetic): {t['requests']}")
    if metrics.get("wiki_dir"):
        lines.append(
            f"- Data provenance: {metrics['sessions_from_wiki']} session(s) from the sessions wiki "
            f"(fully indexed; costs priced from wiki token counts at current rates), "
            f"{metrics['sessions_from_jsonl']} parsed from JSONL (wiki: `{metrics['wiki_dir']}`)"
        )
    lines.append(f"- **Total counterfactual cost: ${t['cost_total']:.2f}**")
    cb = t["cost_breakdown"]
    lines.append(
        f"  - input ${cb.get('cost_input', 0):.2f} | cache_read ${cb.get('cost_cache_read', 0):.2f} | "
        f"cache_write_5m ${cb.get('cost_cache_write_5m', 0):.2f} | "
        f"cache_write_1h ${cb.get('cost_cache_write_1h', 0):.2f} | output ${cb.get('cost_output', 0):.2f}"
    )
    lines.append(f"- Aggregate gap-rewrite waste: ${t['wasted_usd']:.2f}")
    lines.append(f"- Sidechain (subagent) requests: {t['sidechain_requests']}, cost ${t['sidechain_cost']:.2f}")
    if metrics["warnings"]:
        lines.append(f"- Parse warnings: {len(metrics['warnings'])} (malformed lines skipped)")
    lines.append("")

    lines.append("## Model mix")
    lines.append("")
    lines.append("| model | requests | input tokens | output tokens | cost |")
    lines.append("|---|---:|---:|---:|---:|")
    for model_key, mv in sorted(metrics["model_mix"].items(), key=lambda kv: -kv[1]["cost"]):
        lines.append(f"| {model_key} | {mv['requests']} | {mv['input_tokens']:,} | {mv['output_tokens']:,} | ${mv['cost']:.2f} |")
    lines.append("")

    lines.append("## Per-project")
    lines.append("")
    lines.append("| project | sessions | requests | cost | waste |")
    lines.append("|---|---:|---:|---:|---:|")
    for proj, pv in sorted(metrics["projects"].items(), key=lambda kv: -kv[1]["cost_total"]):
        lines.append(f"| {proj} | {pv['sessions']} | {pv['requests']} | ${pv['cost_total']:.2f} | ${pv['wasted_usd']:.2f} |")
    lines.append("")

    top_n = metrics["sessions"][: args.top]
    lines.append(f"## Top {len(top_n)} sessions by cost")
    lines.append("")
    lines.append("| session | project | requests | cost | waste | flags |")
    lines.append("|---|---|---:|---:|---:|---|")
    for s in top_n:
        short_id = s["session_id"][:8]
        flags = ", ".join(s["flags"]) if s["flags"] else "-"
        lines.append(f"| {short_id} | {s['project']} | {s['requests']} | ${s['cost_total']:.2f} | ${s['wasted_usd']:.2f} | {flags} |")
    lines.append("")

    flagged = [s for s in metrics["sessions"] if s["flags"]]
    lines.append(f"## Flagged sessions ({len(flagged)})")
    lines.append("")
    if flagged:
        lines.append("| session | project | flags |")
        lines.append("|---|---|---|")
        for s in flagged:
            lines.append(f"| {s['session_id'][:8]} | {s['project']} | {', '.join(s['flags'])} |")
    else:
        lines.append("None.")
    lines.append("")

    hint_sessions = {s["session_id"]: s for s in top_n}
    for s in flagged:
        hint_sessions.setdefault(s["session_id"], s)

    lines.append("## Next step: extract commands")
    lines.append("")
    lines.append("Run these to get condensed transcripts for the sessions above:")
    lines.append("")
    lines.append("```")
    for s in hint_sessions.values():
        lines.append(f"python parse_sessions.py extract \"{s['path']}\"")
    lines.append("```")
    lines.append("")

    with open(path, "w", **FILE_ENCODING_KWARGS) as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated, {len(text)} chars total]"


def extract_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    pricing = load_pricing(args.pricing_file, args.sonnet5_intro)
    warnings = []

    # First pass: determine, for each (message.id, requestId), which line
    # (by uuid) is the retained "last occurrence".
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
        print(f"# NOTE: this session has {len(subagent_files)} subagent transcript(s) not shown here"
              " (they cost separately in scan's sidechain totals). Extract them individually if needed:")
        for sf in subagent_files:
            print(f"#   {sf}")
    print("")

    for obj in iter_jsonl(path, warnings):
        rtype = obj.get("type")
        ts = obj.get("timestamp", "")

        if rtype == "user":
            msg = obj.get("message") or {}
            text, tool_result_blocks = extract_user_content_blocks(msg)
            if obj.get("isMeta"):
                continue
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
                is_error = block.get("is_error")
                err_flag = " ERROR" if is_error else ""
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
            continue  # superseded duplicate; skip

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
            model_key, is_unknown = resolve_model_key(model)
            costed = compute_request_cost(usage, model_key, pricing)
            unk = " [UNKNOWN MODEL, priced as opus]" if is_unknown else ""
            sidechain_flag = " [sidechain]" if obj.get("isSidechain") else ""
            print(
                f"  USAGE: in={costed['input_tokens']} cache_read={costed['cache_read_tokens']} "
                f"cache_write(5m={costed['cache_write_5m_tokens']},1h={costed['cache_write_1h_tokens']}) "
                f"out={costed['output_tokens']} cost=${costed['cost_total']:.4f}{unk}{sidechain_flag}"
            )
        print("")

    if warnings:
        print(f"# {len(warnings)} warning(s) during parse:", file=sys.stderr)
        for w in warnings:
            print(f"#   {w}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="parse_sessions.py",
        description="Deterministic parser for Claude Code session JSONL transcripts (session-retro skill).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Scan the full session corpus and write metrics.json + summary.md")
    scan_p.add_argument("--claude-dir", default="~/.claude", help="Path to the Claude Code home dir (default: ~/.claude)")
    scan_p.add_argument("--project", action="append", help="Only include projects whose dir name contains this substring (repeatable)")
    scan_p.add_argument("--since", help="Only include sessions active on/after this date (YYYY-MM-DD)")
    scan_p.add_argument("--out", help="Output directory (default: <claude-dir>/session-retro/runs/<timestamp>)")
    scan_p.add_argument("--top", type=int, default=10, help="Number of top sessions by cost to include in summary.md (default: 10)")
    scan_p.add_argument("--sonnet5-intro", action="store_true", help="Price Sonnet 5 at the intro rate ($2/$10 per MTok) instead of standard ($3/$15)")
    scan_p.add_argument("--pricing-file", help="Path to a JSON file overriding entries in the default pricing table")
    scan_p.add_argument("--wiki-dir", help="Sessions-wiki folder; fully-indexed sessions are read from wiki metrics instead of JSONL (default: default_wiki_dir from <claude-dir>/sessions-wiki/config.json)")
    scan_p.add_argument("--no-wiki", action="store_true", help="Ignore any sessions wiki; always parse JSONL sources")
    scan_p.set_defaults(func=scan_command)

    extract_p = sub.add_parser("extract", help="Print a condensed transcript of one session JSONL file")
    extract_p.add_argument("session_file", help="Path to the session .jsonl file")
    extract_p.add_argument("--max-text", type=int, default=800, help="Max chars for assistant text blocks (default: 800)")
    extract_p.add_argument("--max-tool", type=int, default=200, help="Max chars for tool_use input / tool_result previews (default: 200)")
    extract_p.add_argument("--sonnet5-intro", action="store_true", help="Price Sonnet 5 at the intro rate for the per-request usage line")
    extract_p.add_argument("--pricing-file", help="Path to a JSON file overriding entries in the default pricing table")
    extract_p.set_defaults(func=extract_command)

    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
