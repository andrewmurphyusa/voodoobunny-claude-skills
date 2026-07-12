"""Cross-script contract test.

wiki_tools.py (build-sessions-wiki) and parse_sessions.py (session-retro) each
carry their own copy of the JSONL parsing / dedup / token-bucketing /
fingerprint logic, so the two skills stay self-contained. That duplication can
silently drift. This test feeds the SAME committed fixture through both and
asserts they agree on the load-bearing quantities: per-model token buckets, the
grand token totals, the source fingerprint, and model-key resolution.

If this test fails, the two implementations have diverged -- reconcile them (and
references/wiki-format.md) before shipping.
"""

import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIKI_SCRIPTS = HERE.parent / "scripts"
RETRO_SCRIPTS = HERE.parents[1] / "session-retro" / "scripts"
sys.path.insert(0, str(WIKI_SCRIPTS))
sys.path.insert(0, str(RETRO_SCRIPTS))

import wiki_tools        # noqa: E402
import parse_sessions    # noqa: E402

MAIN_SESSION = HERE / "fixtures" / "projects" / "c--fixture-proj" / \
    "11111111-1111-1111-1111-111111111111.jsonl"

TOKEN_KEYS = ("input_tokens", "cache_read_tokens", "cache_write_5m_tokens",
              "cache_write_1h_tokens", "output_tokens")


class TestParserContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wiki_metrics, _ = wiki_tools.compute_session_metrics(MAIN_SESSION)
        pricing = parse_sessions.load_pricing(None, False)
        args = types.SimpleNamespace(since_dt=None)
        cls.retro_record = parse_sessions.process_session_file(
            MAIN_SESSION, "c--fixture-proj", args, pricing, warnings=[])

    def test_token_totals_agree(self):
        for k in TOKEN_KEYS:
            self.assertEqual(
                self.wiki_metrics["tokens"][k], self.retro_record["tokens"][k],
                msg=f"token bucket {k} disagrees between the two parsers")

    def test_request_and_sidechain_counts_agree(self):
        self.assertEqual(self.wiki_metrics["requests"], self.retro_record["requests"])
        self.assertEqual(self.wiki_metrics["sidechain_requests"],
                         self.retro_record["sidechain_requests"])

    def test_per_model_token_sums_agree(self):
        # wiki keeps main/sidechain mixes separate; retro merges them. Compare sums.
        wiki_by_model = {}
        for mix in ("model_mix_main", "model_mix_sidechain"):
            for mk, b in self.wiki_metrics[mix].items():
                acc = wiki_by_model.setdefault(mk, {"input_tokens": 0, "output_tokens": 0})
                acc["input_tokens"] += b["input_tokens"]
                acc["output_tokens"] += b["output_tokens"]
        for mk, rb in self.retro_record["model_mix"].items():
            self.assertIn(mk, wiki_by_model)
            self.assertEqual(wiki_by_model[mk]["input_tokens"], rb["input_tokens"])
            self.assertEqual(wiki_by_model[mk]["output_tokens"], rb["output_tokens"])

    def test_fingerprint_agrees(self):
        wiki_mt, wiki_sz, _ = wiki_tools.session_source_stat(MAIN_SESSION)
        retro_mt, retro_sz = parse_sessions.session_source_stat(MAIN_SESSION)
        self.assertEqual((wiki_mt, wiki_sz), (retro_mt, retro_sz))

    def test_model_key_resolution_agrees(self):
        for name in ["claude-fable-5", "claude-mythos-5", "claude-opus-4-8",
                     "claude-sonnet-5", "claude-haiku-4-5", "weird-model", None]:
            self.assertEqual(wiki_tools.resolve_model_key(name),
                             parse_sessions.resolve_model_key(name),
                             msg=f"resolve_model_key disagrees for {name!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
