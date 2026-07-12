"""Cross-skill contract test.

Since the shared-core refactor, wiki_tools.py (build-sessions-wiki) and
parse_sessions.py (session-retro) both parse through session_core.py -- so
drift is structurally prevented. This test now guards the two remaining
integration seams:

  1. session-retro's sys.path shim actually imports the shared session_core.
  2. the JSONL cost path and the WIKI cost path in parse_sessions produce an
     identical priced record for the same session (the two paths converge on
     record_from_core_metrics / price_token_buckets).

It also re-checks that the pricing-free wiki metrics and the priced retro record
agree on token buckets and the source fingerprint.
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIKI_SCRIPTS = HERE.parent / "scripts"
RETRO_SCRIPTS = HERE.parents[1] / "session-retro" / "scripts"
sys.path.insert(0, str(WIKI_SCRIPTS))
sys.path.insert(0, str(RETRO_SCRIPTS))

import session_core as sc  # noqa: E402
import wiki_tools          # noqa: E402
import parse_sessions      # noqa: E402

MAIN_SESSION = HERE / "fixtures" / "projects" / "c--fixture-proj" / \
    "11111111-1111-1111-1111-111111111111.jsonl"

TOKEN_KEYS = ("input_tokens", "cache_read_tokens", "cache_write_5m_tokens",
              "cache_write_1h_tokens", "output_tokens")


class TestSharedCoreImport(unittest.TestCase):
    def test_retro_uses_same_session_core(self):
        # The shim must import the one canonical module, not a copy.
        self.assertIs(parse_sessions.sc, sc)


class TestParserContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wiki_metrics, _ = wiki_tools.compute_session_metrics(MAIN_SESSION)
        cls.pricing = parse_sessions.load_pricing(None, False)
        cls.retro_record = parse_sessions.process_session_file(
            MAIN_SESSION, "c--fixture-proj", None, cls.pricing, warnings=[])

    def test_token_totals_agree(self):
        for k in TOKEN_KEYS:
            self.assertEqual(
                self.wiki_metrics["tokens"][k], self.retro_record["tokens"][k],
                msg=f"token bucket {k} disagrees between wiki metrics and retro record")

    def test_request_and_sidechain_counts_agree(self):
        self.assertEqual(self.wiki_metrics["requests"], self.retro_record["requests"])
        self.assertEqual(self.wiki_metrics["sidechain_requests"],
                         self.retro_record["sidechain_requests"])

    def test_fingerprint_agrees(self):
        wiki_mt, wiki_sz, _ = wiki_tools.session_source_stat(MAIN_SESSION)
        retro_mt, retro_sz, _ = parse_sessions.session_source_stat(MAIN_SESSION)
        self.assertEqual((wiki_mt, wiki_sz), (retro_mt, retro_sz))

    def test_jsonl_and_wiki_cost_paths_agree(self):
        # Feed the same pricing-free core metrics through the wiki path (as if
        # read from a page) and the jsonl path; the priced records must match.
        jsonl_record = self.retro_record
        wiki_record = parse_sessions.record_from_core_metrics(
            self.wiki_metrics, "c--fixture-proj", MAIN_SESSION, self.pricing, None,
            source="wiki", wiki_page="sessions/x.md")
        self.assertEqual(jsonl_record["cost_total"], wiki_record["cost_total"])
        self.assertEqual(jsonl_record["cost"], wiki_record["cost"])
        self.assertEqual(jsonl_record["wasted_usd"], wiki_record["wasted_usd"])
        self.assertEqual(jsonl_record["model_mix"], wiki_record["model_mix"])
        self.assertEqual(jsonl_record["flags"], wiki_record["flags"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
