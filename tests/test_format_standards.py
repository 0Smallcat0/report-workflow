"""Format-standards regressions: page numbers, TOC placement/language, math, CJK front matter."""
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from report_workflow.nodes.docx_render import (
    _REFERENCE_DOC,
    _find_pandoc,
    _inject_toc,
    _render_via_pandoc,
    _toc_openxml_block,
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
