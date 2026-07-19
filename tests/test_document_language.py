"""Tests for document-language detection and localized section headings."""
import unittest

from report_workflow.language import (
    ZH_ORDINAL_PREFIX_RE,
    count_words,
    derived_section_title,
    detect_document_language,
    localized_section_title,
)
from report_workflow.nodes.abstract_check import _count_words
from report_workflow.nodes.docx_render import (
    _localize_reference_heading,
    _split_body_references,
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


ACADEMIC_BLUEPRINT = {
    "section_order": ["abstract", "introduction", "references"],
    "sections": {
        "abstract": {"section_id": "abstract", "title": "Abstract", "title_zh": "摘要", "required": True},
        "introduction": {"section_id": "introduction", "title": "Introduction", "title_zh": "緒論", "required": True},
        "references": {"section_id": "references", "title": "References", "title_zh": "參考文獻", "required": True},
    },
}


class SpecialHeadingLocalizationTest(unittest.TestCase):
    def test_zh_abstract_and_references_headings_localized(self):
        markdown = (
            f"# Abstract\n\n{ZH_BODY}\n\n# Introduction\n\n{ZH_BODY}\n\n"
            f"## References\n\n- Li, J. (2023). HaluEval benchmark. EMNLP, 6449-6464.\n"
        )
        normalized, issues = normalize_heading_contract(markdown, ACADEMIC_BLUEPRINT)
        self.assertEqual(issues, [])
        self.assertIn("# 摘要", normalized)
        self.assertIn("# 1. 緒論", normalized)
        self.assertIn("## 參考文獻", normalized)
        self.assertNotIn("# Abstract", normalized)

    def test_english_abstract_and_references_unchanged(self):
        body = "This study evaluates deterministic gates. " * 8
        markdown = (
            f"# Abstract\n\n{body}\n\n# Introduction\n\n{body}\n\n"
            f"## References\n\n- Li, J. (2023). HaluEval benchmark. EMNLP, 6449-6464.\n"
        )
        normalized, issues = normalize_heading_contract(markdown, ACADEMIC_BLUEPRINT)
        self.assertEqual(issues, [])
        self.assertIn("# Abstract", normalized)
        self.assertIn("## References", normalized)


class CjkWordCountTest(unittest.TestCase):
    def test_chinese_abstract_counts_characters(self):
        self.assertGreaterEqual(_count_words(ZH_BODY), 60)

    def test_english_count_unchanged(self):
        self.assertEqual(_count_words("The quick brown fox jumps over 3 dogs."), 8)

    def test_abstract_check_delegates_to_shared_counter(self):
        self.assertEqual(_count_words(ZH_BODY), count_words(ZH_BODY))

    def test_chinese_academic_title_is_not_undercounted(self):
        # scholarly_quality flags academic titles outside 5..22 words; a
        # Chinese title counted by \b\w+\b scored 1 and was always flagged.
        title = "大型語言模型文件產生管線之反幻覺驗證閘門"
        self.assertGreaterEqual(count_words(title), 5)
        self.assertLessEqual(count_words(title), 22)


class ZhOrdinalPrefixTest(unittest.TestCase):
    def test_strips_dun_and_paren_forms(self):
        self.assertEqual(ZH_ORDINAL_PREFIX_RE.sub("", "一、緒論"), "緒論")
        self.assertEqual(ZH_ORDINAL_PREFIX_RE.sub("", "（三）研究方法"), "研究方法")
        self.assertEqual(ZH_ORDINAL_PREFIX_RE.sub("", "十二、附錄"), "附錄")

    def test_leaves_plain_heading_untouched(self):
        self.assertEqual(ZH_ORDINAL_PREFIX_RE.sub("", "結論"), "結論")


class ReferenceHeadingRenderTest(unittest.TestCase):
    def test_split_body_references_matches_zh_heading(self):
        md = (
            f"# 1. 緒論\n\n{ZH_BODY}\n\n## 參考文獻\n\n"
            "- Li, J. (2023). HaluEval benchmark. In Proceedings of EMNLP 2023, 6449-6464.\n"
        )
        remaining, refs = _split_body_references(md)
        self.assertNotIn("參考文獻", remaining)
        self.assertIn("HaluEval benchmark", refs)

    def test_localize_reference_heading_for_zh_document(self):
        ref_md = "## References\n\n- Li, J. (2023). HaluEval benchmark. EMNLP, 6449-6464.\n"
        localized = _localize_reference_heading(ref_md, ZH_BODY, ACADEMIC_BLUEPRINT)
        self.assertTrue(localized.startswith("## 參考文獻"))
        self.assertNotIn("## References", localized)

    def test_localize_reference_heading_noop_for_english(self):
        ref_md = "## References\n\n- Li, J. (2023). HaluEval benchmark. EMNLP, 6449-6464.\n"
        body = "This study evaluates deterministic gates. " * 8
        self.assertEqual(_localize_reference_heading(ref_md, body, ACADEMIC_BLUEPRINT), ref_md)

    def test_internal_document_refs_kept_for_non_academic_profiles(self):
        md = f"# 1. 緒論\n\n{ZH_BODY}\n\n## 參考文獻\n\n- 資料管線監控告警系統導入提案(核准版)。\n- 內部維運手冊,第三章:告警分級規則。\n"
        _, strict_refs = _split_body_references(md, strict_refs=True)
        self.assertEqual(strict_refs, "")
        _, loose_refs = _split_body_references(md, strict_refs=False)
        self.assertIn("導入提案", loose_refs)
        self.assertIn("維運手冊", loose_refs)


if __name__ == "__main__":
    unittest.main()
