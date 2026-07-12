"""Unit tests for parse_sessions.py -- the session-retro pricing + scan layer.

Parsing itself is covered by build-sessions-wiki/tests/test_session_core.py; this
suite targets what session-retro adds on top: pricing, the unified
record_from_core_metrics path (JSONL and wiki), the wiki fingerprint/fallback
logic, and scan aggregation. stdlib unittest only.

Reuses the committed synthetic fixture from the build-sessions-wiki skill.
"""

import sys
import platform
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RETRO_SCRIPTS = HERE.parent / "scripts"
WIKI_SCRIPTS = HERE.parents[1] / "build-sessions-wiki" / "scripts"
sys.path.insert(0, str(WIKI_SCRIPTS))
sys.path.insert(0, str(RETRO_SCRIPTS))

import session_core as sc      # noqa: E402
import parse_sessions as ps    # noqa: E402

FIXTURES = HERE.parents[1] / "build-sessions-wiki" / "tests" / "fixtures"
FIXTURE_PROJ = FIXTURES / "projects" / "c--fixture-proj"
MAIN_SESSION = FIXTURE_PROJ / "11111111-1111-1111-1111-111111111111.jsonl"
EMPTY_SESSION = FIXTURE_PROJ / "22222222-2222-2222-2222-222222222222.jsonl"

PRICING = ps.load_pricing(None, False)


class TestPricing(unittest.TestCase):
    def test_price_token_buckets_fable(self):
        c = ps.price_token_buckets(
            {"input_tokens": 112, "output_tokens": 33, "cache_write_1h_tokens": 60000},
            "fable", PRICING)
        self.assertAlmostEqual(c["cost_input"], 112 * 10 / 1e6)
        self.assertAlmostEqual(c["cost_output"], 33 * 50 / 1e6)
        self.assertAlmostEqual(c["cost_cache_write_1h"], 60000 * 2.0 * 10 / 1e6)
        self.assertAlmostEqual(c["cost_total"], 0.00112 + 0.00165 + 1.2)

    def test_unknown_model_priced_as_opus(self):
        rates = ps.safe_rates("not-a-real-key", PRICING)
        self.assertEqual(rates, ps.rates_for("opus", PRICING))

    def test_sonnet5_intro_toggle(self):
        std = ps.load_pricing(None, False)
        intro = ps.load_pricing(None, True)
        self.assertEqual(ps.rates_for("sonnet5", std), (3.0, 15.0))
        self.assertEqual(ps.rates_for("sonnet5", intro), (2.0, 10.0))


class TestRecordFromCoreMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core, _ = sc.compute_session_metrics(MAIN_SESSION)

    def test_jsonl_record_costs(self):
        rec = ps.record_from_core_metrics(self.core, "c--fixture-proj", MAIN_SESSION,
                                          PRICING, None, source="jsonl")
        self.assertEqual(rec["cost_total"], 1.2028)          # 0.00112 + 0.00165 + 1.2
        self.assertEqual(rec["wasted_usd"], 1.14)            # 60000*(2.0-0.1)*10/1e6
        self.assertEqual(rec["flags"], ["GAP_REWRITES"])     # dollar-based gap flag ($1.14 > $0.50)
        self.assertEqual(rec["sidechain_cost"], 0.0002)      # 7*10 + 3*50 per Mtok
        self.assertEqual(rec["source"], "jsonl")
        self.assertEqual(rec["model_mix"]["fable"]["requests"], 3)

    def test_empty_and_before_since(self):
        empty_core, _ = sc.compute_session_metrics(EMPTY_SESSION)
        self.assertEqual(ps.record_from_core_metrics(empty_core, "p", EMPTY_SESSION,
                         PRICING, None, source="jsonl"), "empty")
        # last_ts of the fixture is 2026-01-01; a 2026-06 cutoff excludes it.
        cutoff = sc.parse_ts("2026-06-01T00:00:00+00:00")
        self.assertEqual(ps.record_from_core_metrics(self.core, "p", MAIN_SESSION,
                         PRICING, cutoff, source="jsonl"), "before_since")

    def test_malformed_core_returns_none(self):
        bad = {"model_mix_main": {"fable": "not-a-dict"}, "last_ts": None}
        self.assertIsNone(ps.record_from_core_metrics(bad, "p", MAIN_SESSION,
                          PRICING, None, source="jsonl"))


class TestWikiPathAndFallback(unittest.TestCase):
    def _write_wiki(self, tmp, metrics_block: str, mtime: int, size: int, machine: str):
        page = Path(tmp) / "sessions" / "c--fixture-proj" / (MAIN_SESSION.stem + ".md")
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            "---\n"
            f"session_id: {MAIN_SESSION.stem}\n"
            "project: c--fixture-proj\n"
            f"machine: {machine}\n"
            f"source_mtime_epoch: {mtime}\n"
            f"source_size: {size}\n"
            "---\n\n"
            "## Metrics (machine-generated, pricing-free)\n\n"
            f"```json\n{metrics_block}\n```\n",
            encoding="utf-8")
        return page

    def test_scan_uses_wiki_for_matching_fingerprint(self):
        import json
        core, _ = sc.compute_session_metrics(MAIN_SESSION)
        mt, size, _ = sc.session_source_stat(MAIN_SESSION)
        with tempfile.TemporaryDirectory() as tmp:
            self._write_wiki(tmp, json.dumps(core), mt, size, platform.node())
            metrics = ps.build_scan_metrics(
                FIXTURES, Path(tmp), PRICING, ["c--fixture-proj"], None, None, None)
            self.assertEqual(metrics["sessions_from_wiki"], 1)
            wiki_rec = next(s for s in metrics["sessions"] if s["source"] == "wiki")
            # Wiki-priced cost matches the JSONL-priced cost for the same session.
            jsonl_rec = ps.record_from_core_metrics(core, "c--fixture-proj", MAIN_SESSION,
                                                    PRICING, None, source="jsonl")
            self.assertEqual(wiki_rec["cost_total"], jsonl_rec["cost_total"])

    def test_scan_falls_back_on_broken_metrics_block(self):
        mt, size, _ = sc.session_source_stat(MAIN_SESSION)
        with tempfile.TemporaryDirectory() as tmp:
            self._write_wiki(tmp, "{ this is not valid json", mt, size, platform.node())
            metrics = ps.build_scan_metrics(
                FIXTURES, Path(tmp), PRICING, ["c--fixture-proj"], None, None, None)
            # Fingerprint matched but block unusable -> parsed from JSONL, warned.
            self.assertEqual(metrics["sessions_from_wiki"], 0)
            self.assertTrue(any("metrics block unusable" in w for w in metrics["warnings"]))

    def test_scan_ignores_wiki_for_other_machine(self):
        import json
        core, _ = sc.compute_session_metrics(MAIN_SESSION)
        mt, size, _ = sc.session_source_stat(MAIN_SESSION)
        with tempfile.TemporaryDirectory() as tmp:
            self._write_wiki(tmp, json.dumps(core), mt, size, "SOME-OTHER-HOST")
            metrics = ps.build_scan_metrics(
                FIXTURES, Path(tmp), PRICING, ["c--fixture-proj"], None, None, None)
            self.assertEqual(metrics["sessions_from_wiki"], 0)


class TestScanAggregation(unittest.TestCase):
    def test_build_scan_metrics_no_wiki(self):
        metrics = ps.build_scan_metrics(
            FIXTURES, None, PRICING, ["c--fixture-proj"], None, None, None)
        self.assertEqual(metrics["sessions_included"], 1)     # main; empty skipped
        self.assertEqual(metrics["sessions_skipped_empty"], 1)
        self.assertEqual(metrics["sessions_from_jsonl"], 1)
        self.assertEqual(metrics["sessions_from_wiki"], 0)
        self.assertEqual(metrics["totals"]["cost_total"], 1.2028)

    def test_render_summary_has_provenance_line(self):
        metrics = ps.build_scan_metrics(
            FIXTURES, Path("some-wiki"), PRICING, ["c--fixture-proj"], None, None, None)
        summary = ps.render_summary(metrics, sonnet5_intro=False, top=10)
        self.assertIn("Data provenance:", summary)
        self.assertIn("counterfactual", summary.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
