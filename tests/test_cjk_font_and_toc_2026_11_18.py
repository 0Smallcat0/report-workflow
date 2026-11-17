"""A CJK font the author can name, and a table of contents they can leave out (2026-11-18)."""
import re
import shutil
import unittest
import zipfile
from unittest.mock import patch

from report_workflow.nodes.docx_render import _inject_toc, run_docx_render
from report_workflow.run_workflow import prepare_workflow
from report_workflow.state import WORKFLOW_RUNS_DIR, ReportState

from tests.test_automation_harness import _all_packages_present

BODY = (
    "# 一、緒論\n\n本研究比較台灣的發電結構與電價，並提出政策組合建議。\n\n"
    "## 背景\n\n夜間尖峰供電是主要缺口。\n"
)


def _render(**spec):
    state = ReportState.new("report", [], "out")
    state.qa["qa_decision"] = "pass"
    state.spec["report_profile"] = "custom"
    state.spec.update(spec)
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    draft = run_dir / "publication.md"
    draft.write_text(BODY, encoding="utf-8")
    state.drafts["publication_style_draft"] = str(draft)
    with patch("report_workflow.nodes.docx_render._validate_docx", return_value=[]):
        result = run_docx_render(state)
    return run_dir, result.output["final_docx_path"]


def _part(docx, name):
    with zipfile.ZipFile(docx) as archive:
        return archive.read(name).decode("utf-8")


@unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
class CjkFontTests(unittest.TestCase):
    def test_default_is_unchanged(self):
        _run, docx = _render()
        styles = _part(docx, "word/styles.xml")
        self.assertNotIn("標楷體", styles)
        self.assertIn("eastAsiaTheme", styles)

    def test_named_font_reaches_defaults_and_every_heading_style(self):
        _run, docx = _render(cjk_font="標楷體")
        styles = _part(docx, "word/styles.xml")
        self.assertIn('w:eastAsia="標楷體"', styles)
        self.assertNotIn("eastAsiaTheme", styles)
        for style_id in ("Normal", "BodyText", "Heading1", "Heading2", "Title", "TOCHeading"):
            block = re.search(rf'<w:style [^>]*w:styleId="{style_id}".*?</w:style>', styles, re.S)
            self.assertIsNotNone(block, style_id)
            if "<w:rFonts" in block.group(0):
                self.assertIn('w:eastAsia="標楷體"', block.group(0), style_id)
        defaults = re.search(r"<w:docDefaults>.*?</w:docDefaults>", styles, re.S).group(0)
        self.assertIn('w:eastAsia="標楷體"', defaults)

    def test_text_is_unchanged(self):
        _run0, plain = _render()
        _run1, fonted = _render(cjk_font="標楷體")
        text = lambda d: re.sub(r"<[^>]+>", "", _part(d, "word/document.xml"))
        self.assertEqual(text(plain), text(fonted))


@unittest.skipUnless(shutil.which("pandoc"), "pandoc not installed")
class TocSwitchTests(unittest.TestCase):
    def test_default_keeps_the_table_of_contents(self):
        run, _docx = _render()
        self.assertIn("TOC \o", (run / "pandoc_input.md").read_text(encoding="utf-8"))

    def test_toc_false_drops_the_contents_page(self):
        run, docx = _render(toc=False)
        self.assertNotIn("TOC \o", (run / "pandoc_input.md").read_text(encoding="utf-8"))
        document = _part(docx, "word/document.xml")
        self.assertNotIn("TOC \o", document)
        self.assertNotIn("目錄", document)

    def test_inject_toc_switch_keeps_the_cover_page_break(self):
        md = "標題\n\n作者\n\n---\n\n# 一、緒論\n\n內文。\n"
        on = _inject_toc(md, True)
        off = _inject_toc(md, True, include_toc=False)
        self.assertIn("TOC \o", on)
        self.assertNotIn("TOC \o", off)
        self.assertIn('w:br w:type="page"', off)
        self.assertEqual(_inject_toc(BODY, False, include_toc=False), BODY)
        self.assertNotIn("openxml", _inject_toc(BODY, False, include_toc=False))


class SpecPlumbingTests(unittest.TestCase):
    def test_prepare_records_the_options(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.txt"
            src.write_text("台灣夜間尖峰供電不足。", encoding="utf-8")
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                state = prepare_workflow(
                    "write", [str(src)], str(Path(tmp) / "out"),
                    report_profile="custom", cjk_font="標楷體", toc=False,
                )
            self.assertEqual(state.spec["cjk_font"], "標楷體")
            self.assertIs(state.spec["toc"], False)
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                default = prepare_workflow("write", [str(src)], str(Path(tmp) / "out2"), report_profile="custom")
            self.assertNotIn("cjk_font", default.spec)
            self.assertNotIn("toc", default.spec)


class CliFlagTests(unittest.TestCase):
    def test_flags_parse_on_prepare_render_and_run(self):
        from report_workflow.cli import build_parser

        parser = build_parser()
        for argv in (["render", "--job-id", "x"], ["run", "--job-id", "x"]):
            args = parser.parse_args(argv + ["--cjk-font", "標楷體", "--no-toc"])
            self.assertEqual((args.cjk_font, args.no_toc), ("標楷體", True))
            args = parser.parse_args(argv)
            self.assertEqual((args.cjk_font, args.no_toc), (None, False))
        args = parser.parse_args(["prepare", "--prompt", "p", "--output", "o", "--cjk-font", "DFKai-SB"])
        self.assertEqual(args.cjk_font, "DFKai-SB")


if __name__ == "__main__":
    unittest.main()
