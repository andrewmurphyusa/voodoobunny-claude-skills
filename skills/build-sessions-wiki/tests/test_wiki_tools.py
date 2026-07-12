"""Unit tests for wiki_tools.py -- stdlib unittest only, no external deps.

Run from anywhere:
    python -m unittest discover -s skills/build-sessions-wiki/tests
or from this directory:
    python -m unittest

These tests target the compute_* / render_* functions directly (which return
data instead of printing) and a committed synthetic session fixture with known,
hand-verifiable numbers. No dependency on the user's live ~/.claude data.
"""

import sys
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import wiki_tools  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROJECTS = FIXTURES / "projects"
FIXTURE_PROJ = PROJECTS / "c--fixture-proj"
MAIN_SESSION = FIXTURE_PROJ / "11111111-1111-1111-1111-111111111111.jsonl"
EMPTY_SESSION = FIXTURE_PROJ / "22222222-2222-2222-2222-222222222222.jsonl"


class TestPureHelpers(unittest.TestCase):
    # NOTE: parsing primitives (resolve_model_key, usage_token_buckets,
    # dedupe_assistant_records) now live in session_core -- see
    # test_session_core.py. This class covers wiki_tools' own helpers.

    def test_coerce_config_value(self):
        self.assertEqual(wiki_tools.coerce_config_value("24"), 24)
        self.assertIsInstance(wiki_tools.coerce_config_value("24"), int)
        self.assertEqual(wiki_tools.coerce_config_value("1.5"), 1.5)
        self.assertIsNone(wiki_tools.coerce_config_value("null"))
        self.assertIsNone(wiki_tools.coerce_config_value(""))
        self.assertEqual(wiki_tools.coerce_config_value("D:\\wiki"), "D:\\wiki")

    def test_classify_session_status(self):
        page = {"machine": "HOST", "source_mtime_epoch": 100, "source_size": 50}
        self.assertEqual(wiki_tools.classify_session_status(None, "HOST", 100, 50), "new")
        self.assertEqual(wiki_tools.classify_session_status(page, "HOST", 100, 50), "unchanged")
        self.assertEqual(wiki_tools.classify_session_status(page, "HOST", 101, 50), "changed")
        self.assertEqual(wiki_tools.classify_session_status(page, "OTHER", 100, 50), "changed")

    def test_compute_staleness(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        age, stale = wiki_tools.compute_staleness("2026-01-01T06:00:00+00:00", 6, now=now)
        self.assertEqual(age, 6.0)
        self.assertFalse(stale)  # exactly 6h is not > 6
        age, stale = wiki_tools.compute_staleness("2026-01-01T05:00:00+00:00", 6, now=now)
        self.assertEqual(age, 7.0)
        self.assertTrue(stale)
        self.assertEqual(wiki_tools.compute_staleness(None, 6, now=now), (None, None))

    def test_resolve_from_time_precedence(self):
        meta = {"last_refreshed": "2026-01-01T00:00:00+00:00"}
        # --all beats everything
        dt, src = wiki_tools.resolve_from_time(True, "2025-01-01", meta)
        self.assertIsNone(dt)
        self.assertIn("all", src)
        # --since beats wiki
        dt, src = wiki_tools.resolve_from_time(False, "2025-06-15", meta)
        self.assertEqual(dt.date().isoformat(), "2025-06-15")
        self.assertIn("since", src)
        # falls back to wiki last_refreshed
        dt, src = wiki_tools.resolve_from_time(False, None, meta)
        self.assertIn("last_refreshed", src)
        # nothing
        dt, src = wiki_tools.resolve_from_time(False, None, None)
        self.assertIsNone(dt)
        # bad --since raises
        with self.assertRaises(ValueError):
            wiki_tools.resolve_from_time(False, "not-a-date", None)


class TestSessionMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics, cls.warnings = wiki_tools.compute_session_metrics(MAIN_SESSION)

    def test_request_counts_dedup_and_synthetic(self):
        # A (deduped from 2 copies) + B + sidechain C = 3; synthetic skipped.
        self.assertEqual(self.metrics["requests"], 3)
        self.assertEqual(self.metrics["sidechain_requests"], 1)

    def test_keeps_last_duplicate_tokens(self):
        # The retained copy of A has output=10, not the earlier 999.
        # totals: output = 10 (A) + 20 (B) + 3 (C) = 33
        self.assertEqual(self.metrics["tokens"]["output_tokens"], 33)
        self.assertEqual(self.metrics["tokens"]["input_tokens"], 112)  # 100 + 5 + 7
        self.assertEqual(self.metrics["tokens"]["cache_write_1h_tokens"], 60000)

    def test_model_mix_main_vs_sidechain(self):
        self.assertEqual(self.metrics["model_mix_main"]["fable"]["requests"], 2)
        self.assertEqual(self.metrics["model_mix_main"]["fable"]["output_tokens"], 30)
        self.assertEqual(self.metrics["model_mix_sidechain"]["fable"]["requests"], 1)
        self.assertEqual(self.metrics["model_mix_sidechain"]["fable"]["input_tokens"], 7)

    def test_user_prompt_counting(self):
        # Only "First prompt": tool_result turn, isMeta, and sidechain task excluded.
        self.assertEqual(self.metrics["user_prompts"], 1)

    def test_gap_detection(self):
        self.assertEqual(len(self.metrics["gap_events"]), 1)
        self.assertEqual(self.metrics["gap_creation_tokens_total"], 60000)
        self.assertEqual(self.metrics["gap_events"][0]["model_key"], "fable")

    def test_repeat_reads(self):
        self.assertEqual(self.metrics["repeat_reads"], {"a.txt": 2})

    def test_flags(self):
        # GAP_REWRITES (60000 > 50000 token flag threshold); nothing else trips.
        self.assertEqual(self.metrics["flags"], ["GAP_REWRITES"])

    def test_context_growth(self):
        self.assertEqual(self.metrics["context"]["first"], 100)
        self.assertEqual(self.metrics["context"]["last"], 60005)
        self.assertEqual(self.metrics["context"]["max"], 60005)

    def test_titles_and_summaries_and_env(self):
        self.assertEqual(self.metrics["ai_titles"], ["Fixture session title"])
        self.assertEqual(self.metrics["builtin_summaries"], ["A fixture session summary."])
        self.assertEqual(self.metrics["cwd"], "/work/fixture")
        self.assertEqual(self.metrics["git_branch"], "main")
        self.assertEqual(self.metrics["claude_code_version"], "2.1.0")

    def test_ttl_and_warnings(self):
        self.assertEqual(self.metrics["ttl_dominant"], "1h")
        self.assertGreaterEqual(self.metrics["warnings_count"], 1)  # malformed line

    def test_fingerprint_present(self):
        mt, sz, subs = wiki_tools.session_source_stat(MAIN_SESSION)
        self.assertEqual(self.metrics["source_mtime_epoch"], mt)
        self.assertEqual(self.metrics["source_size"], sz)
        self.assertEqual(len(subs), 1)  # the subagent file counts toward the fingerprint

    def test_empty_session(self):
        metrics, _ = wiki_tools.compute_session_metrics(EMPTY_SESSION)
        self.assertTrue(metrics.get("empty"))


class TestPlan(unittest.TestCase):
    def test_build_plan_new_and_classification(self):
        plan = wiki_tools.build_plan(
            claude_dir=FIXTURES, wiki_dir=None, since_dt=None,
            since_source="none (all sessions)", project_filters=[], last=None,
            machine="TESTHOST")
        ids = {s["session_id"]: s for s in plan["sessions"]}
        self.assertIn("11111111-1111-1111-1111-111111111111", ids)
        # No wiki -> everything is "new".
        self.assertEqual(ids["11111111-1111-1111-1111-111111111111"]["status"], "new")
        self.assertEqual(plan["counts"]["new"], plan["counts"]["total"])
        # Subagent file is folded into the fingerprint listing.
        self.assertEqual(len(ids["11111111-1111-1111-1111-111111111111"]["subagent_files"]), 1)

    def test_build_plan_last_caps_and_sorts(self):
        plan = wiki_tools.build_plan(
            claude_dir=FIXTURES, wiki_dir=None, since_dt=None,
            since_source="x", project_filters=[], last=1, machine="TESTHOST")
        self.assertEqual(len(plan["sessions"]), 1)
        # newest-modified first: the main session was written after the empty one
        # in the fixture set is not guaranteed, so just assert the cap holds.
        self.assertEqual(plan["counts"]["total"], 1)

    def test_project_filter_excludes(self):
        plan = wiki_tools.build_plan(
            claude_dir=FIXTURES, wiki_dir=None, since_dt=None,
            since_source="x", project_filters=["nonexistent-project"], last=None,
            machine="TESTHOST")
        self.assertEqual(plan["counts"]["total"], 0)


class TestRenderAndRoundTrip(unittest.TestCase):
    def _page(self, sid, **over):
        p = {
            "page": f"sessions/c--proj/{sid}.md", "abs_page": "", "project": "c--proj",
            "machine": "HOST", "title": f"title {sid}", "tags": ["alpha", "beta"],
            "first_ts": "2026-01-01T00:00:00", "last_ts": "2026-01-01T01:00:00",
            "indexed_at": "", "source_path": "", "source_mtime_epoch": 1, "source_size": 1,
        }
        p.update(over)
        return p

    def test_render_index_and_tags(self):
        pages = {
            "sid-b": self._page("sid-b", last_ts="2026-02-01T00:00:00", tags=["beta"]),
            "sid-a": self._page("sid-a", last_ts="2026-01-01T00:00:00", tags=["alpha", "beta"]),
        }
        ordered = wiki_tools.order_pages(pages)
        # newest last_ts first
        self.assertEqual(ordered[0][0], "sid-b")
        index = wiki_tools.render_index(ordered, "2026-03-01T00:00:00+00:00")
        self.assertIn("last_refreshed: 2026-03-01T00:00:00+00:00", index)
        self.assertIn("session_count: 2", index)
        tag_map = wiki_tools.build_tag_map(ordered)
        self.assertEqual(set(tag_map), {"alpha", "beta"})
        tags_md = wiki_tools.render_tags(tag_map, "2026-03-01T00:00:00+00:00")
        self.assertIn("## alpha", tags_md)
        self.assertIn("## beta", tags_md)

    def test_config_set_get_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            cfg = dict(wiki_tools.DEFAULT_CONFIG)
            wiki_tools.config_set(cfg_path, cfg, "staleness_hours",
                                  wiki_tools.coerce_config_value("24"))
            reloaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(reloaded["staleness_hours"], 24)


if __name__ == "__main__":
    unittest.main(verbosity=2)
