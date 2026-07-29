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
        # References is a top-level section, at the same level as its siblings.
        self.assertIn("# 參考文獻", normalized)
        self.assertNotIn("## 參考文獻", normalized)
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
        self.assertIn("# References", normalized)
        self.assertNotIn("## References", normalized)


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


class TemplateFieldKeyTest(unittest.TestCase):
    """A Chinese template's placeholders must be visible to the report.

    _normalize_field_key kept only [a-z0-9], so 課程名稱 normalised to the
    empty string and was dropped: the field-fill report found no placeholders
    in a template full of them and signed off with status pass.
    """

    def test_a_chinese_field_name_survives_normalisation(self):
        from report_workflow.artifact_packaging.template_reports import _normalize_field_key

        self.assertEqual(_normalize_field_key("課程名稱"), "課程名稱")
        self.assertEqual(_normalize_field_key("Course Name"), "course_name")

    def test_chinese_placeholders_are_found(self):
        from report_workflow.artifact_packaging.template_reports import (
            _extract_template_placeholders,
        )

        found = _extract_template_placeholders("課程：{{課程名稱}}\n學號：{{學號}}")
        self.assertEqual(sorted(item["key"] for item in found), ["學號", "課程名稱"])


class BaseSectionsReadabilityTest(unittest.TestCase):
    """The file the revision brief sends the author to must be readable.

    A change must quote original_text exactly or it will not apply, and the
    author copies it from base_document_sections.json. Written with escapes, a
    Chinese document reads as \\uXXXX there — while its sibling titles file,
    written one line later, was already readable.
    """

    def test_sections_are_written_unescaped(self):
        import tempfile
        from pathlib import Path
        from report_workflow.state import ReportState, WORKFLOW_RUNS_DIR
        from report_workflow.nodes.base_document_parse import run_base_document_parse

        tmpdir = Path(tempfile.mkdtemp())
        src = tmpdir / "base.md"
        src.write_text("# 結果\n\n導入後不良率下降。\n", encoding="utf-8")
        state = ReportState.new("revise", [], str(tmpdir / "out"))
        state.spec["task_intent"] = "revise_existing"
        state.sources["source_registry"] = [{
            "source_id": "S", "file_name": src.name, "file_path": str(src),
            "file_type": "md", "artifact_role": "base_document",
        }]
        state = run_base_document_parse(state)

        raw = (WORKFLOW_RUNS_DIR / state.job_id / "base_document_sections.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("導入後不良率下降。", raw)
        self.assertNotIn("\\u5c0e", raw)


class RevisedHeadingLanguageTest(unittest.TestCase):
    """A revised Chinese report kept its own section headings.

    The abstract and reference headings were hardcoded English while every
    other section took its heading from the base document, so revising a
    Chinese report renamed 摘要 to "Abstract" and 參考文獻 to "References" in
    the delivered document. Nothing downstream localizes a body heading back.
    """

    def _revise(self, headings: dict[str, str], target: str) -> list[str]:
        import json
        import tempfile
        from pathlib import Path
        from report_workflow.state import ReportState, WORKFLOW_RUNS_DIR
        from report_workflow.nodes.base_document_parse import run_base_document_parse
        from report_workflow.nodes.revision_apply import run_revision_apply

        tmpdir = tempfile.mkdtemp()
        src = Path(tmpdir) / "base.md"
        src.write_text(
            "\n\n".join(f"# {h}\n\n{body}" for h, body in headings.items()),
            encoding="utf-8",
        )
        state = ReportState.new("revise", [], str(Path(tmpdir) / "out"))
        state.spec["task_intent"] = "revise_existing"
        state.sources["source_registry"] = [{
            "source_id": "S", "file_name": src.name, "file_path": str(src),
            "file_type": "md", "artifact_role": "base_document",
        }]
        state = run_base_document_parse(state)
        section_id = next(
            sid for sid, body in state.sources["base_document_sections"].items()
            if body.strip().endswith(target)
        )
        (WORKFLOW_RUNS_DIR / state.job_id / "revision_plan.json").write_text(
            json.dumps({"changes": [{
                "section_id": section_id, "change_type": "replace",
                "original_text": target, "new_text": target + target[-1],
                "claim_ids": ["c1"], "evidence_ids": ["e1"],
            }]}, ensure_ascii=False), encoding="utf-8")
        state = run_revision_apply(state)
        merged = Path(state.drafts["merged_draft_md"]).read_text(encoding="utf-8")
        return [line[2:].strip() for line in merged.splitlines() if line.startswith("# ")]

    def test_chinese_headings_survive_a_revision(self):
        order = self._revise(
            {"摘要": "本報告檢視導入成效。", "討論": "樣本期間偏短。",
             "參考文獻": "1. 內部月報，2025。"},
            "樣本期間偏短。",
        )
        self.assertIn("摘要", order)
        self.assertIn("參考文獻", order)
        self.assertNotIn("Abstract", order)
        self.assertNotIn("References", order)

    def test_english_headings_are_unchanged(self):
        order = self._revise(
            {"Abstract": "This report reviews it.", "Discussion": "The window is short.",
             "References": "1. Internal report, 2025."},
            "The window is short.",
        )
        self.assertIn("Abstract", order)
        self.assertIn("References", order)


class FigureCaptionRecognitionTest(unittest.TestCase):
    """A caption the tool itself writes must be recognised as a caption.

    Both figure checkers reported "no caption" on captions that were there:
    the period style in every language, and every Chinese caption in the
    scholarly checker. A review issue raised on every figure of every report
    is noise the author learns to skip.
    """

    STYLES = (
        ("Figure 1. Throughput vs load.", "As Figure 1 shows, it rises."),
        ("Figure 1: Throughput vs load.", "As Figure 1 shows, it rises."),
        ("圖 1. 流量與有效度。", "如圖 1 所示。"),
        ("圖 1：流量與有效度。", "如圖 1 所示。"),
        ("图 1. 流量与有效度。", "如图 1 所示。"),
    )

    def test_every_caption_style_is_recognised(self):
        from report_workflow.nodes.figure_quality import (
            _extract_known_captions,
            _extract_known_prose_refs,
        )
        from report_workflow.nodes.scholarly_quality import _figure_mentions

        for caption, prose in self.STYLES:
            with self.subTest(caption):
                body = f"[FIGURE: 1]\n\n{caption}\n\n{prose}"
                self.assertIn("1", _extract_known_captions(body, {"1"}))
                self.assertIn("1", _extract_known_prose_refs(body, {"1"}))
                _placeholder, _prose, has_caption = _figure_mentions(body, "1")
                self.assertTrue(has_caption)

    def test_a_missing_caption_is_still_reported(self):
        from report_workflow.nodes.figure_quality import _extract_known_captions
        from report_workflow.nodes.scholarly_quality import _figure_mentions

        body = "[FIGURE: 1]\n\n數值上升。"
        self.assertEqual(_extract_known_captions(body, {"1"}), set())
        self.assertEqual(_figure_mentions(body, "1"), (True, False, False))


if __name__ == "__main__":
    unittest.main()
