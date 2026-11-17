"""A title that already carries its ordinal is not numbered a second time (2026-11-18)."""
import json
import tempfile
import unittest
from pathlib import Path

from report_workflow.artifact_lint import _lint_outline
from report_workflow.language import has_heading_ordinal
from report_workflow.nodes.heading_contract_check import normalize_heading_contract
from report_workflow.state import ReportState


def _blueprint(title):
    return {
        "section_order": ["introduction", "methods", "references"],
        "sections": {
            "introduction": {"title": "Introduction", "title_zh": "緒論", "required": True},
            "methods": {"title": title, "title_zh": title, "required": True},
            "references": {"title": "References", "title_zh": "參考文獻", "required": True},
        },
    }


class HeadingOrdinalTests(unittest.TestCase):
    def _headings(self, title):
        md = (
            "# 緒論\n\n本研究比較台灣的發電結構與電價並提出政策組合建議。\n\n"
            f"# {title}\n\n本節說明資料來源、計算方式與限制條件的處理方式。\n\n# 參考文獻\n"
        )
        normalized, _ = normalize_heading_contract(md, _blueprint(title))
        return [line for line in normalized.splitlines() if line.startswith("# ")]

    def test_prefixed_titles_are_not_numbered_twice(self):
        for title in ("二、台灣電力現況", "第二章 台灣電力現況", "（二）台灣電力現況", "2. 台灣電力現況", "十二、台灣電力現況"):
            self.assertEqual(self._headings(title)[1], f"# {title}", title)

    def test_plain_titles_are_still_numbered(self):
        self.assertEqual(self._headings("台灣電力現況"), ["# 一、緒論", "# 二、台灣電力現況", "# 參考文獻"])

    def test_detector(self):
        for yes in ("一、緒論", "第一章 緒論", "第3節 方法", "（一）緒論", "1. Intro", "1.2 Intro", "2、方法"):
            self.assertTrue(has_heading_ordinal(yes), yes)
        for no in ("緒論", "2025 年回顧", "一帶一路", "Introduction"):
            self.assertFalse(has_heading_ordinal(no), no)

    def test_validate_warns_not_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = ReportState.new("report", [], str(Path(tmp) / "out"))
            state.plan["blueprint"] = _blueprint("方法")
            run_dir = Path(tmp)
            (run_dir / "outline.json").write_text(json.dumps({"sections": {
                "introduction": {"title": "二、緒論", "claim_ids": []},
                "methods": {"title": "方法", "claim_ids": []},
            }}), encoding="utf-8")
            issues = []
            _lint_outline(state, run_dir, issues, set())
            hits = [i for i in issues if "ordinal" in i.message or "序號" in i.message]
            self.assertEqual(len(hits), 1, [i.message for i in issues])
            self.assertEqual(hits[0].severity, "warning")
            self.assertIn("introduction", hits[0].json_path)


if __name__ == "__main__":
    unittest.main()
