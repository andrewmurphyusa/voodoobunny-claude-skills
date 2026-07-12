"""Unit tests for session_core.py -- the shared, pricing-free parsing core.

These target the Tier-1 seam (metrics_from_records over in-memory record lists)
and the Tier-2 pure sub-analyses directly, so each parsing rule is covered by a
tiny three-line case with no on-disk fixture. stdlib unittest only.
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import session_core as sc  # noqa: E402


# --- tiny record factories -------------------------------------------------

def u(input=0, output=0, cache_read=0, w5=0, w1h=0):
    return {
        "input_tokens": input, "output_tokens": output,
        "cache_read_input_tokens": cache_read,
        "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1h},
    }


def asst(msg_id, req_id, uuid, ts, usage, model="claude-fable-5", content=None,
         sidechain=False, **env):
    rec = {
        "type": "assistant", "timestamp": ts, "requestId": req_id, "uuid": uuid,
        "isSidechain": sidechain,
        "message": {"id": msg_id, "model": model, "content": content or [], "usage": usage},
    }
    rec.update(env)
    return rec


def user_prompt(ts, text, meta=False, sidechain=False):
    return {"type": "user", "timestamp": ts, "isMeta": meta, "isSidechain": sidechain,
            "message": {"role": "user", "content": text}}


def tool_result_turn(ts, tool_use_id, content="result"):
    return {"type": "user", "timestamp": ts,
            "message": {"role": "user", "content": [{"type": "tool_result",
                        "tool_use_id": tool_use_id, "content": content}]}}


def read_tool_use(tid, file_path):
    return {"type": "tool_use", "id": tid, "name": "Read", "input": {"file_path": file_path}}


def metrics(records, **over):
    kw = dict(session_id="s", project="proj", path="p", source_mtime_epoch=0,
              source_size=0, subagent_files=[], machine="TEST", generated_at="T",
              warnings_count=0)
    kw.update(over)
    return sc.metrics_from_records(records, **kw)


class TestPrimitives(unittest.TestCase):
    def test_resolve_model_key(self):
        self.assertEqual(sc.resolve_model_key("claude-fable-5"), ("fable", False))
        self.assertEqual(sc.resolve_model_key("claude-mythos-5"), ("fable", False))
        self.assertEqual(sc.resolve_model_key("claude-opus-4-8"), ("opus", False))
        self.assertEqual(sc.resolve_model_key("claude-sonnet-5"), ("sonnet5", False))
        self.assertEqual(sc.resolve_model_key("claude-haiku-4-5"), ("haiku", False))
        self.assertEqual(sc.resolve_model_key("mystery"), ("opus", True))
        self.assertEqual(sc.resolve_model_key(None), ("opus", True))

    def test_usage_token_buckets_breakdown(self):
        b = sc.usage_token_buckets(u(input=100, output=20, cache_read=5, w5=3, w1h=7))
        self.assertEqual((b["input_tokens"], b["cache_read_tokens"], b["cache_write_5m_tokens"],
                          b["cache_write_1h_tokens"], b["output_tokens"]), (100, 5, 3, 7, 20))

    def test_usage_token_buckets_1h_fallback(self):
        b = sc.usage_token_buckets({"cache_creation_input_tokens": 500})
        self.assertEqual(b["cache_write_1h_tokens"], 500)
        self.assertEqual(b["cache_write_5m_tokens"], 0)

    def test_dedupe_keeps_last(self):
        recs = [asst("m1", "r1", "u1", "2026-01-01T00:00:00Z", u(output=999)),
                asst("m1", "r1", "u2", "2026-01-01T00:00:00Z", u(output=10))]
        out = sc.dedupe_assistant_records(recs)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["uuid"], "u2")


class TestSubAnalyses(unittest.TestCase):
    def _mcr(self, ts, w1h=0, w5=0, model="fable"):
        return {"ts": datetime.fromisoformat(ts), "model_key": model,
                "buckets": {"cache_write_5m_tokens": w5, "cache_write_1h_tokens": w1h}}

    def test_detect_gap_events_1h(self):
        chain = [self._mcr("2026-01-01T00:00:00+00:00"),
                 self._mcr("2026-01-01T02:00:00+00:00", w1h=60000)]  # 2h gap
        events, total = sc.detect_gap_events(chain, "1h")
        self.assertEqual(len(events), 1)
        self.assertEqual(total, 60000)
        self.assertEqual(events[0]["model_key"], "fable")

    def test_detect_gap_events_below_threshold(self):
        # 10-minute gap is under the 1h threshold -> no event even with big write.
        chain = [self._mcr("2026-01-01T00:00:00+00:00"),
                 self._mcr("2026-01-01T00:10:00+00:00", w1h=60000)]
        events, total = sc.detect_gap_events(chain, "1h")
        self.assertEqual(events, [])
        self.assertEqual(total, 0)

    def test_compute_flags(self):
        self.assertEqual(sc.compute_flags(gap_triggered=True, read_file_counts={},
                         large_tool_results=[], context_last=0, total_requests=1,
                         unknown_models=[]), ["GAP_REWRITES"])
        self.assertIn("REPEAT_READS", sc.compute_flags(gap_triggered=False,
                      read_file_counts={"a": 3}, large_tool_results=[], context_last=0,
                      total_requests=1, unknown_models=[]))
        self.assertIn("LONG_CONTEXT", sc.compute_flags(gap_triggered=False,
                      read_file_counts={}, large_tool_results=[], context_last=200_000,
                      total_requests=1, unknown_models=[]))
        self.assertIn("UNKNOWN_MODEL", sc.compute_flags(gap_triggered=False,
                      read_file_counts={}, large_tool_results=[], context_last=0,
                      total_requests=1, unknown_models=["x"]))

    def test_context_growth(self):
        self.assertEqual(sc.context_growth([100, 500, 300]), {"first": 100, "max": 500, "last": 300})
        self.assertEqual(sc.context_growth([]), {"first": 0, "max": 0, "last": 0})

    def test_count_user_prompts(self):
        recs = [user_prompt("t", "real"), user_prompt("t", "meta", meta=True),
                user_prompt("t", "sidechain task", sidechain=True),
                tool_result_turn("t", "tu1")]
        self.assertEqual(sc.count_user_prompts(recs), 1)


class TestMetricsFromRecords(unittest.TestCase):
    def test_dedup_synthetic_sidechain(self):
        recs = [
            asst("m1", "r1", "u1", "2026-01-01T00:00:00Z", u(input=100, output=999)),
            asst("m1", "r1", "u2", "2026-01-01T00:00:00Z", u(input=100, output=10)),
            asst("mS", "rS", "uS", "2026-01-01T00:05:00Z", u(input=1, output=1), model="<synthetic>"),
            asst("m3", "r3", "u3", "2026-01-01T00:10:00Z", u(input=7, output=3), sidechain=True),
        ]
        m = metrics(recs)
        self.assertEqual(m["requests"], 2)          # dup collapsed, synthetic skipped
        self.assertEqual(m["sidechain_requests"], 1)
        self.assertEqual(m["tokens"]["output_tokens"], 13)   # 10 (last dup) + 3
        self.assertEqual(m["model_mix_main"]["fable"]["output_tokens"], 10)
        self.assertEqual(m["model_mix_sidechain"]["fable"]["input_tokens"], 7)

    def test_gap_and_flag(self):
        recs = [
            asst("m1", "r1", "u1", "2026-01-01T00:00:00Z", u(input=100)),
            asst("m2", "r2", "u2", "2026-01-01T02:00:00Z", u(input=5, w1h=60000)),
        ]
        m = metrics(recs)
        self.assertEqual(len(m["gap_events"]), 1)
        self.assertEqual(m["gap_creation_tokens_total"], 60000)
        self.assertEqual(m["flags"], ["GAP_REWRITES"])
        self.assertEqual(m["context"]["last"], 60005)

    def test_repeat_reads_no_flag(self):
        recs = [
            asst("m1", "r1", "u1", "2026-01-01T00:00:00Z", u(input=1),
                 content=[read_tool_use("t1", "a.txt")]),
            asst("m2", "r2", "u2", "2026-01-01T00:00:05Z", u(input=1),
                 content=[read_tool_use("t2", "a.txt")]),
        ]
        m = metrics(recs)
        self.assertEqual(m["repeat_reads"], {"a.txt": 2})
        self.assertNotIn("REPEAT_READS", m["flags"])  # needs >=3 reads or >=5 files

    def test_prompt_counting(self):
        recs = [
            user_prompt("2026-01-01T00:00:00Z", "real question"),
            user_prompt("2026-01-01T00:00:01Z", "meta", meta=True),
            tool_result_turn("2026-01-01T00:00:02Z", "t1"),
            asst("m1", "r1", "u1", "2026-01-01T00:00:03Z", u(input=1)),
        ]
        self.assertEqual(metrics(recs)["user_prompts"], 1)

    def test_empty_session(self):
        m = metrics([user_prompt("2026-01-01T00:00:00Z", "aborted before any assistant turn")])
        self.assertTrue(m.get("empty"))

    def test_injected_machine_and_generated_at(self):
        m = metrics([asst("m1", "r1", "u1", "2026-01-01T00:00:00Z", u(input=1))],
                    machine="HOSTX", generated_at="2026-01-01T00:00:00+00:00")
        self.assertEqual(m["machine"], "HOSTX")
        self.assertEqual(m["generated_at"], "2026-01-01T00:00:00+00:00")


class TestRenderExtractAndPrompts(unittest.TestCase):
    def test_render_extract_skips_superseded_dup(self):
        recs = [
            user_prompt("2026-01-01T00:00:00Z", "hello"),
            asst("m1", "r1", "u1", "2026-01-01T00:00:01Z", u(input=1), content=[{"type": "text", "text": "OLD"}]),
            asst("m1", "r1", "u2", "2026-01-01T00:00:01Z", u(input=1), content=[{"type": "text", "text": "NEW"}]),
        ]
        out = sc.render_extract(recs, "s.jsonl", "/p/s.jsonl", [])
        self.assertIn("NEW", out)
        self.assertNotIn("OLD", out)  # only the retained (last) copy is rendered
        self.assertIn("USER: hello", out)

    def test_render_extract_usage_suffix(self):
        recs = [asst("m1", "r1", "u1", "2026-01-01T00:00:00Z", u(input=1))]
        out = sc.render_extract(recs, "s.jsonl", "/p/s.jsonl", [],
                                usage_suffix=lambda obj, usage: " COST_HERE")
        self.assertIn("COST_HERE", out)

    def test_collect_and_render_prompts(self):
        recs = [user_prompt("t1", "first"), tool_result_turn("t2", "x"),
                user_prompt("t3", "second", meta=True), user_prompt("t4", "third")]
        prompts = sc.collect_prompts_from_records(recs)
        self.assertEqual([p[1] for p in prompts], ["first", "third"])
        md = sc.render_prompts_markdown(prompts)
        self.assertIn("## Prompts (verbatim, 2 total)", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
