"""Format-standards regressions: page numbers, TOC placement/language, math, CJK front matter."""
import re
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from report_workflow.errors import QAHardBlockError
from report_workflow.nodes.docx_render import (
    _REFERENCE_DOC,
    _find_pandoc,
    _inject_toc,
    _render_via_pandoc,
    _resolve_reference_doc,
    _toc_openxml_block,
    reference_docx_error,
)
from report_workflow.nodes.front_matter_build import (
    _parse_affiliation_from_user_prompt,
    _parse_author_from_user_prompt,
    _parse_title_from_user_prompt,
)


class TocInjectionTest(unittest.TestCase):
    def test_zh_document_gets_zh_toc_after_front_matter(self):
        md = (
            "# 管線監控導入報告\n\n作者:王小明\n\n---\n\n# 緒論\n\n"
            "本研究說明監控管線的導入流程與觀察結果,並整理後續維運建議。"
            "全文以中文撰寫,涵蓋方法、結果與討論。"
        )
        out = _inject_toc(md, has_front_matter=True)
        self.assertIn("目錄", out)
        self.assertIn('TOC \\o "1-3"', out)
        # Title page stays first; body follows the TOC.
        self.assertLess(out.index("作者"), out.index("目錄"))
        self.assertLess(out.index("目錄"), out.index("緒論"))

    def test_en_document_gets_en_toc(self):
        md = "Title page\n\n---\n\n# Introduction\n\nEnglish body text for detection."
        out = _inject_toc(md, has_front_matter=True)
        self.assertIn("Table of Contents", out)
        self.assertNotIn("目錄", out)

    def test_without_front_matter_toc_leads_document(self):
        md = "# Introduction\n\nBody."
        out = _inject_toc(md, has_front_matter=False)
        self.assertTrue(out.startswith("```{=openxml}"))
        self.assertIn("# Introduction", out)

    def test_block_uses_toc_heading_style_and_field(self):
        block = _toc_openxml_block("en", page_break_before=True)
        self.assertIn('w:pStyle w:val="TOCHeading"', block)
        self.assertIn('w:fldCharType="begin"', block)
        self.assertIn('w:br w:type="page"', block)


class ReferenceTemplateTest(unittest.TestCase):
    def test_template_footer_has_page_field(self):
        with zipfile.ZipFile(_REFERENCE_DOC) as z:
            footers = [n for n in z.namelist() if re.match(r"word/footer\d*\.xml", n)]
            self.assertTrue(footers, "reference.docx must carry a footer for page numbers")
            self.assertTrue(
                any("PAGE" in z.read(n).decode("utf-8") for n in footers),
                "footer must contain a PAGE field",
            )


class CoverTocPlacementTest(unittest.TestCase):
    def test_cover_promoted_to_title_page_with_toc_after(self):
        md = (
            "# 封面\n\n本報告為機械工程實驗課程之實驗報告,依據講義與量測數據撰寫。\n\n"
            "# 1. 實驗目的\n\n量測懸臂樑自由端撓度並與理論比較,驗證線性關係與誤差來源。"
        )
        out = _inject_toc(md, has_front_matter=False, cover_title="封面")
        # The cover heading is dropped (a title page does not label itself,
        # and without a Heading 1 it stays out of the TOC field).
        self.assertNotIn("# 封面", out)
        self.assertIn('w:jc w:val="center"', out)
        self.assertIn("目錄", out)
        self.assertLess(out.index("本報告為"), out.index("目錄"))
        self.assertLess(out.index("目錄"), out.index("實驗目的"))

    def test_unrelated_first_heading_keeps_toc_on_top(self):
        md = "# Introduction\n\nBody text.\n\n# Methods\n\nMore body."
        out = _inject_toc(md, has_front_matter=False, cover_title="封面")
        self.assertTrue(out.startswith("```{=openxml}"))

    def test_revised_document_title_leads_and_toc_follows(self):
        md = "# My Report Title\n\n# Introduction\n\nBody text for the report."
        out = _inject_toc(md, has_front_matter=False, title_leads=True)
        self.assertLess(out.index("My Report Title"), out.index("Table of Contents"))
        self.assertLess(out.index("Table of Contents"), out.index("Introduction"))


class TableFigureTitleTest(unittest.TestCase):
    def test_table_title_uses_columns(self):
        from report_workflow.nodes.figure_recommend import _human_figure_title

        title = _human_figure_title(
            "table",
            "",
            "",
            {"columns": ["荷重(N)", "實測撓度(mm)", "理論撓度(mm)", "誤差(%)"]},
            "量測數據.csv",
            "",
        )
        self.assertIn("實測撓度", title)
        self.assertIn("依荷重", title)
        self.assertNotIn("view of", title)


class DerivedStatsEvidenceTest(unittest.TestCase):
    def _registry(self, cols):
        import json

        rows = [
            {cols[0]: "5", cols[1]: "1.52", cols[2]: "1.45", cols[3]: "4.8"},
            {cols[0]: "10", cols[1]: "3.01", cols[2]: "2.90", cols[3]: "3.8"},
            {cols[0]: "15", cols[1]: "4.48", cols[2]: "4.35", cols[3]: "3.0"},
        ]
        blocks = [
            {"block_type": "csv_row", "content": json.dumps(r, ensure_ascii=False)}
            for r in rows
        ]
        return [{
            "source_id": "s1",
            "file_name": "m.csv",
            "file_path": "m.csv",
            "file_type": "csv",
            "parsed_content": blocks,
        }]

    def test_en_measurement_columns_produce_citable_stats(self):
        from report_workflow.nodes.evidence_normalize import _derived_stats_units

        units = _derived_stats_units(
            self._registry(
                ["Load (N)", "Measured deflection (mm)", "Theoretical deflection (mm)", "Error (%)"]
            ),
            "2026-07-22T00:00:00+00:00",
        )
        self.assertEqual(len(units), 2)
        regression = units[0]
        self.assertEqual(regression["evidence_grade"], "high")
        self.assertIn("least-squares slope", regression["content"])
        self.assertIn("R²", regression["content"])
        self.assertEqual(regression["derivation"]["method"], "least_squares_fit")
        self.assertIn("mean", units[1]["content"])

    def test_zh_columns_produce_zh_content(self):
        from report_workflow.nodes.evidence_normalize import _derived_stats_units

        units = _derived_stats_units(
            self._registry(["荷重(N)", "實測撓度(mm)", "理論撓度(mm)", "誤差(%)"]),
            "2026-07-22T00:00:00+00:00",
        )
        self.assertEqual(len(units), 2)
        self.assertIn("最小平方法", units[0]["content"])
        self.assertIn("平均", units[1]["content"])

    def test_unrelated_columns_add_nothing(self):
        from report_workflow.nodes.evidence_normalize import _derived_stats_units

        units = _derived_stats_units(
            self._registry(["A", "B", "C", "D"]), "2026-07-22T00:00:00+00:00"
        )
        self.assertEqual(units, [])


class ReaderRubricTest(unittest.TestCase):
    PROFILES = [
        "engineering_lab_report",
        "academic_paper",
        "proposal",
        "business_report",
        "admissions_report",
        "admissions_project_report",
        "custom",
    ]

    def test_every_profile_has_a_rubric(self):
        from report_workflow.nodes.agent_tasks import _reader_rubric_section

        for profile in self.PROFILES:
            section = _reader_rubric_section(profile)
            self.assertIn("How the Reader Grades This", section)
            self.assertIn("entry ticket", section)

    def test_lab_rubric_demands_quantified_comparison(self):
        from report_workflow.nodes.agent_tasks import _reader_rubric_section

        section = _reader_rubric_section("engineering_lab_report")
        self.assertIn("R²", section)
        self.assertIn("professor", section)


class StructureGuidanceTest(unittest.TestCase):
    def test_paragraph_rule_for_every_profile(self):
        from report_workflow.nodes.agent_tasks import _structure_guidance

        for profile in ReaderRubricTest.PROFILES:
            section = _structure_guidance(profile)
            self.assertIn("Context → Content → Conclusion", section)
            self.assertIn("Kording", section)

    def test_lab_discussion_recipe_present(self):
        from report_workflow.nodes.agent_tasks import _structure_guidance

        section = _structure_guidance("engineering_lab_report")
        self.assertIn("quantitatively with theory", section)
        self.assertIn("verdict", section)

    def test_business_lines_lead_with_the_answer(self):
        from report_workflow.nodes.agent_tasks import _structure_guidance

        self.assertIn("Pyramid Principle", _structure_guidance("business_report"))
        self.assertIn("SCQA", _structure_guidance("proposal"))


class EnglishTitleLocalizationTest(unittest.TestCase):
    def test_cjk_only_blueprint_title_falls_back_for_english(self):
        from report_workflow.language import localized_section_title

        self.assertEqual(
            localized_section_title({"title": "封面"}, "cover", "en"), "Cover"
        )
        self.assertEqual(
            localized_section_title({"title": "結果與討論"}, "results_discussion", "en"),
            "Results Discussion",
        )

    def test_zh_document_still_gets_chinese_title(self):
        from report_workflow.language import localized_section_title

        self.assertEqual(
            localized_section_title(
                {"title": "Cover", "title_zh": "封面"}, "cover", "zh"
            ),
            "封面",
        )

    def test_engineering_blueprint_is_bilingual(self):
        import report_workflow

        blueprint = (
            Path(report_workflow.__file__).parent
            / "blueprints"
            / "engineering_lab_report.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("title: Cover", blueprint)
        self.assertIn("title_zh: 封面", blueprint)
        self.assertIn("title: Results and Discussion", blueprint)
        self.assertIn("title_zh: 結果與討論", blueprint)


class NativeTableRenderTest(unittest.TestCase):
    def _manifest(self):
        return {
            "figures": [
                {
                    "figure_id": "1",
                    "figure_type": "table",
                    "title": "各級荷重之實測與理論撓度",
                    "render_mode": "native_table",
                    "data": {
                        "columns": ["荷重(N)", "實測撓度(mm)"],
                        "rows": [["5", "1.52"], ["10", "3.01"]],
                    },
                }
            ]
        }

    def test_zh_native_table_markdown(self):
        from report_workflow.nodes.docx_render import _replace_figure_placeholders

        md = "五級荷重的量測結果整理如下表,實測撓度與理論撓度的誤差均低於檢查門檻。\n\n[FIGURE:1]\n"
        out, replaced, unresolved = _replace_figure_placeholders(md, self._manifest())
        self.assertEqual(replaced, 1)
        self.assertEqual(unresolved, [])
        self.assertIn("表 1. 各級荷重之實測與理論撓度", out)
        self.assertIn("| 荷重(N) | 實測撓度(mm) |", out)
        self.assertIn("| 5 | 1.52 |", out)
        self.assertNotIn("[FIGURE:1]", out)

    def test_en_native_table_caption(self):
        from report_workflow.nodes.docx_render import _replace_figure_placeholders

        md = "The measured deflections are summarized in the table below.\n\n[FIGURE:1]\n"
        manifest = self._manifest()
        manifest["figures"][0]["title"] = "Deflection summary"
        out, replaced, _ = _replace_figure_placeholders(md, manifest)
        self.assertEqual(replaced, 1)
        self.assertIn("Table 1. Deflection summary", out)


class FigureCaptionLanguageTest(unittest.TestCase):
    def test_zh_caption_prefix(self):
        from report_workflow.nodes.docx_render import _figure_alt_text

        alt = _figure_alt_text(
            {"figure_id": "1", "title": "實測與理論撓度比較"}, "1", language="zh"
        )
        self.assertTrue(alt.startswith("圖 1."), alt)

    def test_en_caption_prefix_unchanged(self):
        from report_workflow.nodes.docx_render import _figure_alt_text

        alt = _figure_alt_text({"figure_id": "1", "title": "Load vs deflection"}, "1")
        self.assertTrue(alt.startswith("Figure 1."), alt)


class ProvenanceGradeTest(unittest.TestCase):
    def test_users_measured_csv_row_grades_high(self):
        from report_workflow.nodes.evidence_normalize import compute_provenance_score

        entry = {"file_type": "csv"}
        block = {
            "content": '{"荷重(N)": "5", "實測撓度(mm)": "1.52", "理論撓度(mm)": "1.45"}',
            "block_type": "csv_row",
        }
        self.assertGreaterEqual(compute_provenance_score(entry, block), 0.7)


class CjkFrontMatterParseTest(unittest.TestCase):
    def test_labelled_cjk_author(self):
        self.assertEqual(_parse_author_from_user_prompt("作者:王小明"), "王小明")
        self.assertEqual(_parse_author_from_user_prompt("Author: 蔡知均"), "蔡知均")

    def test_english_author_still_parses(self):
        self.assertEqual(_parse_author_from_user_prompt("Author: Jane Smith"), "Jane Smith")

    def test_cjk_title_and_affiliation(self):
        self.assertEqual(_parse_title_from_user_prompt("標題:拉伸試驗報告"), "拉伸試驗報告")
        self.assertEqual(
            _parse_affiliation_from_user_prompt("單位:國立成功大學機械工程學系"),
            "國立成功大學機械工程學系",
        )


class CustomReferenceDocResolutionTest(unittest.TestCase):
    def test_defaults_to_builtin_template(self):
        self.assertEqual(_resolve_reference_doc({}), _REFERENCE_DOC)
        self.assertEqual(_resolve_reference_doc({"reference_docx_path": "  "}), _REFERENCE_DOC)

    def test_valid_custom_template_wins(self):
        spec = {"reference_docx_path": str(_REFERENCE_DOC)}
        self.assertEqual(_resolve_reference_doc(spec), _REFERENCE_DOC)

    def test_missing_custom_template_hard_blocks(self):
        with self.assertRaises(QAHardBlockError):
            _resolve_reference_doc({"reference_docx_path": r"Z:\no\such\template.docx"})

    def test_error_messages(self):
        self.assertIn("not found", reference_docx_error(Path(r"Z:\no\such\template.docx")))
        with tempfile.TemporaryDirectory() as td:
            txt = Path(td) / "styles.txt"
            txt.write_text("not a docx", encoding="utf-8")
            self.assertIn("not a .docx", reference_docx_error(txt))
            fake = Path(td) / "fake.docx"
            fake.write_text("still not a zip", encoding="utf-8")
            self.assertIn("not a valid docx", reference_docx_error(fake))
        self.assertIsNone(reference_docx_error(_REFERENCE_DOC))


@unittest.skipIf(_find_pandoc() is None, "pandoc not installed")
class CustomReferenceDocRenderTest(unittest.TestCase):
    def test_output_follows_user_template_styles(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as td:
            custom = Path(td) / "corporate.docx"
            shutil.copy2(_REFERENCE_DOC, custom)
            doc = Document(str(custom))
            doc.styles["Heading 1"].font.name = "Arial Black"
            doc.save(str(custom))

            md = Path(td) / "doc.md"
            md.write_text("# Section\n\nBody text.\n", encoding="utf-8")
            out = Path(td) / "doc.docx"
            self.assertTrue(_render_via_pandoc(str(md), str(out), reference_doc=custom))
            with zipfile.ZipFile(out) as z:
                styles = z.read("word/styles.xml").decode("utf-8")
            self.assertIn("Arial Black", styles)


@unittest.skipIf(_find_pandoc() is None, "pandoc not installed")
class PandocFormatIntegrationTest(unittest.TestCase):
    def test_math_toc_and_footer_in_rendered_docx(self):
        with tempfile.TemporaryDirectory() as td:
            md = Path(td) / "doc.md"
            md.write_text(
                _inject_toc(
                    "Title page\n\n---\n\n# Methods\n\nInline $E = mc^2$ math.\n",
                    has_front_matter=True,
                ),
                encoding="utf-8",
            )
            out = Path(td) / "doc.docx"
            self.assertTrue(_render_via_pandoc(str(md), str(out)))
            with zipfile.ZipFile(out) as z:
                doc = z.read("word/document.xml").decode("utf-8")
                self.assertIn("<m:oMath", doc, "TeX math must render to OMML")
                self.assertIn("TOC", doc)
                self.assertTrue(
                    [n for n in z.namelist() if n.startswith("word/footer")],
                    "page-number footer must survive into rendered output",
                )


if __name__ == "__main__":
    unittest.main()
