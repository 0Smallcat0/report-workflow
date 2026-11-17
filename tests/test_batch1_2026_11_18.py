"""Fixes found by writing a Chinese report end to end (2026-11-18, batch 1)."""
import unittest

from report_workflow.nodes.factuality_check import (
    _check_content_overlap,
    numbers_with_spans,
)


def _figures(text):
    return [(n, u) for n, u, _s, _e in numbers_with_spans(text)[1]]


def _fe(claim, evidence):
    return _check_content_overlap(
        {"claim_id": "c1", "claim_text": claim, "claim_type": "factual", "evidence_ids": ["E1"]},
        {"evidence_id": "E1", "content": evidence, "granularity": "paragraph", "source_file_name": "a.pdf"},
    )


class PerUnitWrittenTwice(unittest.TestCase):
    def test_per_prefix_plus_written_rate_is_not_doubled(self):
        self.assertEqual(_figures("台電每度售電成本 4.1007 元/度"), [("4.1007", "元/度")])
        self.assertEqual(_figures("每公斤 5 元/公斤"), [("5", "元/公斤")])
        self.assertEqual(_figures("每噸 500 美元/噸"), [("500", "美元/噸")])

    def test_per_prefix_with_plain_money_is_a_rate(self):
        self.assertEqual(_figures("每度平均電價 3.9674 元"), [("3.9674", "元/度")])
        self.assertEqual(_figures("每度平均售電價格約為 3.9674 元"), [("3.9674", "元/度")])

    def test_both_spellings_match_a_rate_claim(self):
        evidence = "單位：元/度 售電成本 4.1007 平均電價 3.9674"
        self.assertEqual(_fe("台電每度售電成本 4.1007 元/度", "台電售電成本 4.1007 元/度"), [])
        self.assertEqual(_fe("平均電價 3.9674 元/度", "每度平均售電價格約為 3.9674 元"), [])
        self.assertEqual(_fe("平均電價 3.9674 元/度", "每度平均電價 3.9674 元/度"), [])
        del evidence

    def test_a_total_is_still_not_a_rate(self):
        self.assertEqual(_figures("每度電的成本結構複雜，售價 500 美元"), [("500", "美元")])


if __name__ == "__main__":
    unittest.main()
