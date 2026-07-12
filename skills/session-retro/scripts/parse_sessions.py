#!/usr/bin/env python3
"""
parse_sessions.py -- deterministic parser for Claude Code session JSONL transcripts.

Part of the session-retro skill. "Scripts count, Fable judges": this script does
all aggregation/arithmetic; nothing here makes qualitative judgments.

Parsing, dedup, token-bucketing, fingerprinting, gap detection, and transcript
rendering are SHARED with the build-sessions-wiki skill via session_core.py
(imported below through a sys.path shim). This file adds only the pricing layer
and the retro-specific scan/report output -- it never re-implements parsing.

The JSONL and wiki paths converge on one pricing function: both produce (or read)
session_core's pricing-free metrics dict, then `record_from_core_metrics` prices
it with the CURRENT pricing table. Dollar figures never come from the wiki.

Two subcommands:

  scan     Walk ~/.claude/projects/**/*.jsonl (or read fully-indexed sessions
           from the wiki), compute per-session metrics + cost, write
           metrics.json + summary.md.
  extract  Print a condensed transcript of one session (with per-request cost).

Python 3, standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared core lives in the sibling build-sessions-wiki skill. The two skills are
# tightly coupled by design (session-retro consumes the wiki's config, pages,
# and metrics format), so we import the one canonical parser rather than keeping
# a second copy that could drift.
# ---------------------------------------------------------------------------
_WIKI_SCRIPTS = Path(__file__).resolve().parents[2] / "build-sessions-wiki" / "scripts"
if str(_WIKI_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_WIKI_SCRIPTS))
try:
    import session_core as sc
except ModuleNotFoundError:
    print("ERROR: could not import session_core.py -- the build-sessions-wiki skill "
          f"must sit beside session-retro (looked in {_WIKI_SCRIPTS}).", file=sys.stderr)
    raise

FILE_ENCODING_KWARGS = sc.FILE_ENCODING_KWARGS
parse_ts = sc.parse_ts
resolve_model_key = sc.resolve_model_key
session_source_stat = sc.session_source_stat  # (mtime, size, subagent_files)

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

# session-retro's GAP_REWRITES flag is dollar-based (unlike the wiki's token
# threshold). Other flag thresholds are shared and live in session_core.
GAP_WASTE_FLAG_USD = 0.50

COST_KEYS = ("cost_input", "cost_cache_read", "cost_cache_write_5m",
             "cost_cache_write_1h", "cost_output", "cost_total")


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


def rates_for(model_key: str, pricing: dict) -> tuple[float, float]:
    if model_key == "sonnet5":
        rates = pricing["sonnet5_effective"]
    else:
        rates = pricing[model_key]
    return rates["input"], rates["output"]


def safe_rates(model_key: str, pricing: dict) -> tuple[float, float]:
    try:
        return rates_for(model_key, pricing)
    except Exception:
        return rates_for("opus", pricing)


def price_token_buckets(buckets: dict, model_key: str, pricing: dict) -> dict:
    """Price the five session_core token buckets with the current table. Shared
    by every cost path (JSONL, wiki, per-request extract) so they cannot drift.
    Returns the cost breakdown plus input_rate (used for gap-waste math)."""
    input_rate, output_rate = safe_rates(model_key, pricing)
    ci = (buckets.get("input_tokens", 0) or 0) * input_rate / 1e6
    ccr = (buckets.get("cache_read_tokens", 0) or 0) * CACHE_READ_MULTIPLIER * input_rate / 1e6
    c5 = (buckets.get("cache_write_5m_tokens", 0) or 0) * CACHE_WRITE_5M_MULTIPLIER * input_rate / 1e6
    c1 = (buckets.get("cache_write_1h_tokens", 0) or 0) * CACHE_WRITE_1H_MULTIPLIER * input_rate / 1e6
    co = (buckets.get("output_tokens", 0) or 0) * output_rate / 1e6
    return {
        "cost_input": ci,
        "cost_cache_read": ccr,
        "cost_cache_write_5m": c5,
        "cost_cache_write_1h": c1,
        "cost_output": co,
        "cost_total": ci + ccr + c5 + c1 + co,
        "input_rate": input_rate,
    }


def compute_request_cost(usage: dict, model_key: str, pricing: dict) -> dict:
    """Token counts + cost breakdown for a single request. Thin wrapper over the
    shared token extractor and pricing. Used by the extract per-request line."""
    buckets = sc.usage_token_buckets(usage)
    costed = price_token_buckets(buckets, model_key, pricing)
    return {**buckets, **costed, "creation_tokens": buckets["cache_write_5m_tokens"] + buckets["cache_write_1h_tokens"]}


def gap_wasted_usd(w5: int, w1h: int, input_rate: float) -> float:
    """Dollars wasted by a gap rewrite: paying cache-write premium instead of a
    cheap cache read. See references/pricing.md."""
    return (w5 * (CACHE_WRITE_5M_MULTIPLIER - CACHE_READ_MULTIPLIER)
            + w1h * (CACHE_WRITE_1H_MULTIPLIER - CACHE_READ_MULTIPLIER)) * input_rate / 1e6


# ---------------------------------------------------------------------------
# record_from_core_metrics -- the single pricing path for BOTH sources
# ---------------------------------------------------------------------------

def record_from_core_metrics(cm: dict, project: str, jsonl_path: Path, pricing: dict,
                             since_dt, *, source: str, wiki_page: str | None = None):
    """Turn session_core's pricing-free metrics dict into a priced session record
    (the shape scan aggregates and summary.md renders). `cm` may be freshly
    computed from JSONL (source="jsonl") or read from a wiki page's metrics block
    (source="wiki"). Returns the record dict, "empty", "before_since", or None if
    the metrics are unusable."""
    if not isinstance(cm, dict):
        return None
    if cm.get("empty"):
        return "empty"
    if not cm.get("model_mix_main") and not cm.get("model_mix_sidechain"):
        return None

    if since_dt is not None:
        last = parse_ts(cm.get("last_ts"))
        if last is not None and last < since_dt:
            return "before_since"

    cost_totals = defaultdict(float)
    model_mix = defaultdict(lambda: {"requests": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0})
    sidechain_cost = 0.0

    for mix_name in ("model_mix_main", "model_mix_sidechain"):
        for mk, b in (cm.get(mix_name) or {}).items():
            if not isinstance(b, dict):
                return None
            costed = price_token_buckets(b, mk, pricing)
            for ck in COST_KEYS:
                cost_totals[ck] += costed[ck]
            mm = model_mix[mk]
            mm["requests"] += b.get("requests", 0) or 0
            mm["cost"] += costed["cost_total"]
            mm["input_tokens"] += b.get("input_tokens", 0) or 0
            mm["output_tokens"] += b.get("output_tokens", 0) or 0
            if mix_name == "model_mix_sidechain":
                sidechain_cost += costed["cost_total"]

    # Gap events: core stores per-event cache-write tokens + model_key; price now.
    gap_events = []
    wasted_usd_total = 0.0
    for ev in cm.get("gap_events") or []:
        input_rate, _ = safe_rates(ev.get("model_key", "opus"), pricing)
        wasted = gap_wasted_usd(ev.get("cache_write_5m_tokens", 0) or 0,
                                ev.get("cache_write_1h_tokens", 0) or 0, input_rate)
        wasted_usd_total += wasted
        gap_events.append({
            "timestamp": ev.get("timestamp"),
            "gap_seconds": ev.get("gap_seconds"),
            "creation_tokens": ev.get("creation_tokens", 0),
            "wasted_usd": round(wasted, 4),
        })

    tokens = {k: (cm.get("tokens") or {}).get(k, 0) or 0 for k in sc.TOKEN_KEYS}
    repeat_reads = cm.get("repeat_reads") or {}
    large_tool_results = cm.get("large_tool_results") or []
    context = cm.get("context") or {"first": 0, "max": 0, "last": 0}
    unknown_models = cm.get("unknown_models") or []
    total_requests = cm.get("requests", 0) or 0

    # Flags: dollar-based GAP_REWRITES for this skill; the rest are shared.
    flags = sc.compute_flags(
        gap_triggered=wasted_usd_total > GAP_WASTE_FLAG_USD,
        read_file_counts=repeat_reads,
        large_tool_results=large_tool_results,
        context_last=context.get("last", 0) or 0,
        total_requests=total_requests,
        unknown_models=unknown_models,
    )

    record = {
        "session_id": cm.get("session_id") or jsonl_path.stem,
        "project": project,
        "path": str(jsonl_path),
        "first_ts": cm.get("first_ts"),
        "last_ts": cm.get("last_ts"),
        "requests": total_requests,
        "sidechain_requests": cm.get("sidechain_requests", 0) or 0,
        "sidechain_cost": round(sidechain_cost, 4),
        "user_prompts": cm.get("user_prompts", 0) or 0,
        "tokens": tokens,
        "cost": {k: round(v, 4) for k, v in cost_totals.items()},
        "cost_total": round(cost_totals["cost_total"], 4),
        "model_mix": {k: {**v, "cost": round(v["cost"], 4)} for k, v in model_mix.items()},
        "unknown_models": sorted(unknown_models),
        "ttl_dominant": cm.get("ttl_dominant", "1h"),
        "gap_events": gap_events,
        "wasted_usd": round(wasted_usd_total, 4),
        "repeat_reads": repeat_reads,
        "large_tool_results": large_tool_results,
        "context": context,
        "flags": flags,
        "source": source,
    }
    if wiki_page is not None:
        record["wiki_page"] = wiki_page
    return record


def process_session_file(path: Path, project: str, since_dt, pricing: dict, warnings: list):
    """JSONL path: read the session, compute pricing-free core metrics, price them.
    Returns a priced record, "empty", or "before_since"."""
    records, w, subs = sc.read_session_records(path)
    warnings.extend(w)
    mtime_epoch, size, _ = sc.session_source_stat(path)
    cm = sc.metrics_from_records(
        records,
        session_id=path.stem,
        project=project,
        path=str(path),
        source_mtime_epoch=mtime_epoch,
        source_size=size,
        subagent_files=subs,
        warnings_count=len(w),
    )
    return record_from_core_metrics(cm, project, path, pricing, since_dt, source="jsonl")


# ---------------------------------------------------------------------------
# sessions-wiki integration
#
# When a session's wiki page fingerprint (machine + source_mtime_epoch +
# source_size across main + subagent files) still matches the live files, scan
# reads the page's pricing-free metrics block instead of re-parsing the JSONL,
# then prices it exactly like the JSONL path. Dollar figures never come from the
# wiki -- only token counts do.
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


def collect_wiki_fingerprints(wiki_dir: Path, warnings: list) -> dict:
    """Map session_id -> fingerprint info for every sessions/**/*.md page."""
    pages = {}
    sessions_dir = wiki_dir / "sessions"
    if not sessions_dir.is_dir():
        warnings.append(f"wiki dir {wiki_dir} has no sessions/ subdir; ignoring wiki")
        return pages
    for md in sorted(sessions_dir.rglob("*.md")):
        fm = sc.parse_frontmatter(md)
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


def session_record_from_wiki(page_path: Path, page_rel: str, project: str, jsonl_path: Path,
                             pricing: dict, since_dt, warnings: list):
    """Read a wiki page's pricing-free metrics block and price it. Returns a
    record, "empty", "before_since", or None if the block is unusable."""
    cm = sc.read_page_metrics_block(page_path, warnings)
    if cm is None:
        return None
    return record_from_core_metrics(cm, project, jsonl_path, pricing, since_dt,
                                    source="wiki", wiki_page=page_rel)


# ---------------------------------------------------------------------------
# scan: build metrics (pure-ish) + render summary (pure) + command wrapper
# ---------------------------------------------------------------------------

def build_scan_metrics(claude_dir: Path, wiki_dir: Path | None, pricing: dict,
                       project_filters: list, since_dt, args_project, args_since,
                       machine: str | None = None, generated_at: str | None = None) -> dict:
    """Enumerate + price every in-scope session and aggregate. Returns the full
    metrics dict; writes nothing. `machine`/`generated_at` injectable for tests."""
    if machine is None:
        machine = sc.platform.node()
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    warnings: list = []
    sessions = []
    skipped_empty = skipped_since = files_seen = 0

    wiki_pages = collect_wiki_fingerprints(wiki_dir, warnings) if wiki_dir else {}

    for project_name, jsonl_path in sc.find_session_files(claude_dir):
        if project_filters and not any(pf in project_name.lower() for pf in project_filters):
            continue
        files_seen += 1

        result = None
        fp = wiki_pages.get(jsonl_path.stem)
        if fp is not None and fp["machine"] == machine:
            mtime_epoch, size, _ = sc.session_source_stat(jsonl_path)
            if fp["source_mtime_epoch"] == mtime_epoch and fp["source_size"] == size:
                result = session_record_from_wiki(fp["abs_page"], fp["page"], project_name,
                                                  jsonl_path, pricing, since_dt, warnings)
                if result is None:
                    warnings.append(f"{fp['abs_page']}: fingerprint matched but metrics "
                                    "block unusable; parsed JSONL instead")

        if result is None:
            result = process_session_file(jsonl_path, project_name, since_dt, pricing, warnings)

        if result == "empty":
            skipped_empty += 1
            continue
        if result == "before_since":
            skipped_since += 1
            continue
        sessions.append(result)

    sessions.sort(key=lambda s: s["cost_total"], reverse=True)

    totals = defaultdict(float)
    tokens_totals = defaultdict(int)
    model_mix_totals = defaultdict(lambda: {"requests": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0})
    projects = defaultdict(lambda: {"sessions": 0, "requests": 0, "cost_total": 0.0, "wasted_usd": 0.0})
    wasted_total = sidechain_cost_total = 0.0
    sidechain_requests_total = requests_total = 0

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

    sessions_from_wiki = sum(1 for s in sessions if s.get("source") == "wiki")

    return {
        "generated_at": generated_at,
        "claude_dir": str(claude_dir),
        "filters": {"project": args_project, "since": args_since},
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


def render_summary(metrics: dict, sonnet5_intro: bool, top: int) -> str:
    """Build summary.md text from a scan metrics dict. Pure."""
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
        f"Sonnet 5 {'intro $2/$10' if sonnet5_intro else 'standard $3/$15'} "
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

    top_n = metrics["sessions"][:top]
    lines.append(f"## Top {len(top_n)} sessions by cost")
    lines.append("")
    lines.append("| session | project | requests | cost | waste | flags |")
    lines.append("|---|---|---:|---:|---:|---|")
    for s in top_n:
        flags = ", ".join(s["flags"]) if s["flags"] else "-"
        lines.append(f"| {s['session_id'][:8]} | {s['project']} | {s['requests']} | ${s['cost_total']:.2f} | ${s['wasted_usd']:.2f} | {flags} |")
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
    return "\n".join(lines)


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

    project_filters = [p.lower() for p in (args.project or [])]
    wiki_dir = resolve_wiki_dir(args)

    metrics = build_scan_metrics(claude_dir, wiki_dir, pricing, project_filters, since_dt,
                                 args.project, args.since)

    if args.out:
        out_dir = Path(args.out).expanduser()
    else:
        run_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = claude_dir / "session-retro" / "runs" / run_stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "metrics.json", "w", **FILE_ENCODING_KWARGS) as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    with open(out_dir / "summary.md", "w", **FILE_ENCODING_KWARGS) as f:
        f.write(render_summary(metrics, args.sonnet5_intro, args.top))

    print(f"Scanned {metrics['files_seen']} session file(s); {metrics['sessions_included']} included, "
          f"{metrics['sessions_skipped_empty']} skipped (empty), "
          f"{metrics['sessions_skipped_before_since']} skipped (before --since).")
    if metrics["warnings"]:
        print(f"{len(metrics['warnings'])} warning(s) -- see metrics.json['warnings'].", file=sys.stderr)
    print(f"Total counterfactual API cost: ${metrics['totals']['cost_total']:.2f}")
    print(f"Output written to: {out_dir}")


# ---------------------------------------------------------------------------
# extract (uses the shared renderer with a cost-annotating usage suffix)
# ---------------------------------------------------------------------------

def extract_command(args):
    path = Path(args.session_file).expanduser()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    pricing = load_pricing(args.pricing_file, args.sonnet5_intro)
    records, warnings = sc.read_jsonl_file(path)
    subagent_files = sc.session_source_stat(path)[2]

    def usage_suffix(obj, usage):
        model = (obj.get("message") or {}).get("model")
        model_key, is_unknown = resolve_model_key(model)
        costed = compute_request_cost(usage, model_key, pricing)
        unk = " [UNKNOWN MODEL, priced as opus]" if is_unknown else ""
        sidechain_flag = " [sidechain]" if obj.get("isSidechain") else ""
        return f" cost=${costed['cost_total']:.4f}{unk}{sidechain_flag}"

    print(sc.render_extract(records, path.name, str(path), subagent_files,
                            max_text=args.max_text, max_tool=args.max_tool,
                            usage_suffix=usage_suffix))
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
