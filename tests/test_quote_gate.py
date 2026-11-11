import tempfile
import unittest
from pathlib import Path

from report_workflow.quote_gate import degrade_claims, ledger_quote_problems, record_attempt


def row(tmp, source_text, content, quote=None, eid="E1"):
    src = Path(tmp) / "s.md"
    src.write_text(source_text, encoding="utf-8")
    return {"evidence_id": eid, "source_file_path": str(src), "content": content,
            "quote": content if quote is None else quote}


class QuoteGateTests(unittest.TestCase):
    def test_contiguous_passes_despite_markup(self):
        with tempfile.TemporaryDirectory() as t:
            r = row(t, "# Title\n\nRevenue grew **12%** in Q3.\n", "Revenue grew 12% in Q3.")
            self.assertEqual(ledger_quote_problems([r]), {})

    def test_spliced_content_fails(self):
        with tempfile.TemporaryDirectory() as t:
            r = row(t, "Revenue grew 12%. Costs fell sharply.", "Revenue grew sharply.")
            self.assertIn("E1", ledger_quote_problems([r]))

    def test_quote_not_in_content_fails(self):
        with tempfile.TemporaryDirectory() as t:
            r = row(t, "alpha beta gamma", "alpha beta gamma", quote="alpha gamma...")
            self.assertIn("E1", ledger_quote_problems([r]))

    def test_two_failures_degrade_to_stats_only(self):
        with tempfile.TemporaryDirectory() as t:
            bad = {"E1": "x"}
            self.assertEqual(record_attempt(t, bad)["status"], "retry")
            self.assertEqual(record_attempt(t, bad)["status"], "stats_only")
            self.assertEqual(record_attempt(t, {})["status"], "ok")
            claims = [{"claim_id": "C1", "claim_type": "factual", "evidence_ids": ["E1"]},
                      {"claim_id": "C2", "claim_type": "statistical", "evidence_ids": ["E1"]}]
            kept, dropped = degrade_claims(claims, bad)
            self.assertEqual([c["claim_id"] for c in kept], ["C2"])
            self.assertEqual(dropped, ["C1"])


if __name__ == "__main__":
    unittest.main()
