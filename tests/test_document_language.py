"""Tests for document-language detection and localized section headings."""
import unittest

from report_workflow.language import (
    derived_section_title,
    detect_document_language,
    localized_section_title,
)
from report_workflow.nodes.heading_contract_check import normalize_heading_contract


BLUEPRINT = {
    "section_order": ["executive_summary", "problem_statement", "appendix"],
    "sections": {
        "executive_summary": {
            "section_id": "executive_summary",
            "title": "Executive Summary",
            "title_zh": "執行摘要",
            "required": True,
        },
        "problem_statement": {
            "section_id": "problem_statement",
            "title": "Problem Statement",
            "title_zh": "問題陳述",
            "required": True,
        },
        "appendix": {
            "section_id": "appendix",
            "title": "Appendix",
            "title_zh": "附錄",
            "required": False,
        },
    },
}

ZH_BODY = (
    "本提案建議導入集中式資料管線監控告警系統。"
    "六月兩次夜間事件皆倚賴人工巡檢發現,平均發現延遲為二十五分鐘。"
    "導入後目標為五分鐘以內發現,監控覆蓋全部排程腳本。"
)


class DetectDocumentLanguageTest(unittest.TestCase):
    def test_chinese_dominant_text_is_zh(self):
        self.assertEqual(detect_document_language(ZH_BODY), "zh")

    def test_english_text_is_en(self):
        text = "This proposal introduces centralized pipeline monitoring. " * 5
        self.assertEqual(detect_document_language(text), "en")

    def test_english_with_few_chinese_names_stays_en(self):
        text = ("The reviewer 蔡知均 approved the monitoring rollout plan. " * 10)
        self.assertEqual(detect_document_language(text), "en")

    def test_empty_text_is_en(self):
        self.assertEqual(detect_document_language(""), "en")


class LocalizedSectionTitleTest(unittest.TestCase):
    def test_zh_prefers_title_zh(self):
        section = BLUEPRINT["sections"]["executive_summary"]
        self.assertEqual(localized_section_title(section, "executive_summary", "zh"), "執行摘要")

    def test_en_uses_title(self):
        section = BLUEPRINT["sections"]["executive_summary"]
        self.assertEqual(
            localized_section_title(section, "executive_summary", "en"), "Executive Summary"
        )

    def test_zh_without_title_zh_falls_back_to_title(self):
        section = {"title": "封面"}
        self.assertEqual(localized_section_title(section, "cover", "zh"), "封面")

    def test_missing_titles_fall_back_to_derived(self):
        self.assertEqual(localized_section_title({}, "scope_deliverables", "zh"), "Scope Deliverables")
        self.assertEqual(derived_section_title("scope_deliverables"), "Scope Deliverables")


class HeadingContractLocalizationTest(unittest.TestCase):
    def test_zh_document_rewrites_english_headings_to_chinese(self):
        markdown = (
            f"# Executive Summary\n\n{ZH_BODY}\n\n"
            f"# Problem Statement\n\n{ZH_BODY}\n"
        )
        normalized, issues = normalize_heading_contract(markdown, BLUEPRINT)
        self.assertEqual(issues, [])
        self.assertIn("# 1. 執行摘要", normalized)
        self.assertIn("# 2. 問題陳述", normalized)
        self.assertNotIn("Executive Summary", normalized)

    def test_zh_document_recognizes_chinese_headings(self):
        markdown = f"# 執行摘要\n\n{ZH_BODY}\n\n# 問題陳述\n\n{ZH_BODY}\n"
        normalized, issues = normalize_heading_contract(markdown, BLUEPRINT)
        self.assertEqual(issues, [])
        self.assertIn("# 1. 執行摘要", normalized)
        self.assertIn("# 2. 問題陳述", normalized)

    def test_zh_ordinal_prefix_headings_are_recognized(self):
        markdown = f"# 一、執行摘要\n\n{ZH_BODY}\n\n# （二）問題陳述\n\n{ZH_BODY}\n"
        normalized, issues = normalize_heading_contract(markdown, BLUEPRINT)
        self.assertEqual(issues, [])
        self.assertIn("# 1. 執行摘要", normalized)
        self.assertIn("# 2. 問題陳述", normalized)

    def test_normalization_is_idempotent_for_zh(self):
        markdown = f"# 執行摘要\n\n{ZH_BODY}\n\n# 問題陳述\n\n{ZH_BODY}\n"
        once, issues_once = normalize_heading_contract(markdown, BLUEPRINT)
        twice, issues_twice = normalize_heading_contract(once, BLUEPRINT)
        self.assertEqual(issues_once, [])
        self.assertEqual(issues_twice, [])
        self.assertEqual(once, twice)

    def test_english_document_keeps_english_titles(self):
        body = "This proposal introduces centralized pipeline monitoring. " * 5
        markdown = f"# Executive Summary\n\n{body}\n\n# Problem Statement\n\n{body}\n"
        normalized, issues = normalize_heading_contract(markdown, BLUEPRINT)
        self.assertEqual(issues, [])
        self.assertIn("# 1. Executive Summary", normalized)
        self.assertIn("# 2. Problem Statement", normalized)
        self.assertNotIn("執行摘要", normalized)

    def test_missing_required_section_still_reported_for_zh(self):
        markdown = f"# 執行摘要\n\n{ZH_BODY}\n"
        _, issues = normalize_heading_contract(markdown, BLUEPRINT)
        self.assertTrue(any("problem_statement" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
