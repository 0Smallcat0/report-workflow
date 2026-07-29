"""Unit tests for revision change types added from the real-proposal dogfood.

Covers the deterministic editorial guard (wording-only changes may not smuggle
in new numbers or quotes) and confirms the content-change applier is unchanged
for the classic replace/insert/delete types.
"""
import unittest

from report_workflow.nodes.revision_apply import (
    _apply_changes,
    _editorial_guard_violations,
)


class EditorialGuardTests(unittest.TestCase):
    def test_pure_rewording_passes(self):
        self.assertEqual(
            _editorial_guard_violations("此設計無需 GPU 訓練模型。", "此設計不需 GPU 訓練模型。"),
            [],
        )

    def test_fullwidth_punctuation_change_passes(self):
        self.assertEqual(
            _editorial_guard_violations("（1）前期規劃；（2）中期執行。", "(1) 前期規劃；(2) 中期執行。"),
            [],
        )

    def test_new_number_is_blocked(self):
        violations = _editorial_guard_violations(
            "錯誤率降至 4.1%,樣本共 42 筆。", "錯誤率有下降,樣本共 42 筆。"
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("4.1", violations[0])

    def test_existing_numbers_may_be_reordered(self):
        self.assertEqual(
            _editorial_guard_violations("由 28 分鐘降至 20 分鐘。", "20 分鐘(原 28 分鐘)。"),
            [],
        )

    def test_new_quoted_span_is_blocked(self):
        violations = _editorial_guard_violations(
            "審查人員稱其「完全可追溯」。", "審查人員給予正面評價。"
        )
        self.assertTrue(any("quoted spans" in v for v in violations))

    def test_retitle_dropping_suffix_passes(self):
        self.assertEqual(
            _editorial_guard_violations("參考文獻方向", "參考文獻方向（示意）"),
            [],
        )


class ApplyChangesRegressionTests(unittest.TestCase):
    def test_replace_delete_insert_still_work(self):
        sections = {"body": "甲段落。乙段落。丙段落。"}
        changes = [
            {"section_id": "body", "change_type": "replace", "original_text": "乙段落。", "new_text": "乙段落(修)。"},
            {"section_id": "body", "change_type": "delete", "original_text": "丙段落。", "new_text": ""},
        ]
        updated, unapplied = _apply_changes(sections, changes)
        self.assertEqual(unapplied, [])
        self.assertEqual(updated["body"], "甲段落。乙段落(修)。")

    def test_structural_types_are_not_content_changes(self):
        # run_revision_apply partitions retitle/remove_section out before
        # calling _apply_changes; feeding one in directly is reported unknown.
        updated, unapplied = _apply_changes(
            {"body": "內容。"},
            [{"section_id": "body", "change_type": "retitle", "new_text": "新標題"}],
        )
        self.assertEqual(updated["body"], "內容。")
        self.assertTrue(any("Unknown change_type" in u for u in unapplied))


class UnknownSectionTests(unittest.TestCase):
    def test_unknown_section_does_not_land_in_the_preamble(self):
        # An anchor-less insert aimed at a section id that does not exist used
        # to be retargeted at the preamble, where the title lift dropped it —
        # the sentence vanished and the diff report still counted it applied.
        sections = {"preamble": "# 標題", "discussion": "討論內容。"}
        updated, unapplied = _apply_changes(
            sections,
            [{
                "section_id": "第四章討論",
                "change_type": "insert",
                "original_text": "",
                "new_text": "第三季不良率為 1.8%。",
            }],
        )
        self.assertEqual(updated["preamble"], "# 標題")
        self.assertEqual(len(unapplied), 1)
        self.assertIn("第四章討論", unapplied[0])
        self.assertIn("discussion", unapplied[0])

    def test_empty_section_still_accepts_an_anchorless_insert(self):
        sections = {"appendix": ""}
        updated, unapplied = _apply_changes(
            sections,
            [{"section_id": "appendix", "change_type": "insert", "original_text": "", "new_text": "附錄。"}],
        )
        self.assertEqual(unapplied, [])
        self.assertIn("附錄。", updated["appendix"])


if __name__ == "__main__":
    unittest.main()
