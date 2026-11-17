import unittest

from report_workflow.nodes.factuality_check import numbers_with_spans


def _figures(text: str) -> list[tuple[str, str]]:
    return [(n, u) for n, u, _s, _e in numbers_with_spans(text)[1]]


class FigureAndTableLabelsAreNotNumbers(unittest.TestCase):
    """「圖 2」「表 1」 name a figure or table; they state no quantity to check."""

    def test_chinese_labels(self):
        for text in ("如圖 2 所示", "見圖2與表1", "表 1 列出結果", "圖表 3 顯示趨勢", "如圖 2-1 與表 3.2"):
            self.assertEqual(_figures(text), [], text)

    def test_english_labels(self):
        for text in ("Figure 2 and Table 1 show", "see Fig. 3 and Table 2a"):
            self.assertEqual(_figures(text), [], text)

    def test_real_numbers_beside_labels_still_count(self):
        self.assertEqual(_figures("表 1 顯示成本為 500 美元"), [("500", "美元")])
        self.assertEqual(_figures("如圖 2，良率 93.5%"), [("93.5", "%")])


class NotebookIsNotACountUnit(unittest.TestCase):
    def test_laptop_word(self):
        self.assertEqual(_figures("搭載 RTX 4060 筆電"), [("4060", "")])

    def test_record_count_keeps_unit(self):
        self.assertEqual(_figures("共 544 筆資料"), [("544", "筆")])


import tempfile
from pathlib import Path

from report_workflow.nodes.figure_recommend import recommend_figures_from_evidence
from report_workflow.state import ReportState


def _recommend(rows):
    with tempfile.TemporaryDirectory() as tmpdir:
        state = ReportState.new("write report", [], str(Path(tmpdir) / "out"))
        state.spec["report_profile"] = "engineering_lab_report"
        state.plan["blueprint"] = {
            "sections": {"results": {}, "data": {}},
            "section_order": ["results", "data"],
        }
        return recommend_figures_from_evidence(state, [{
            "evidence_id": "E1", "source_id": "p", "source_file_name": "sens.csv",
            "granularity": "table", "content": "sensitivity grid", "table_data": rows,
        }])[0]


def _long_grid(nx=10, ny=11):
    rows = [["Capex multiplier", "Price multiplier", "IRR (%)"]]
    for i in range(nx):
        for j in range(ny):
            rows.append([f"{0.5 + 0.1 * i:.1f}", f"{0.5 + 0.1 * j:.1f}", f"{5 + i * 1.3 + j * 0.9 + (i * j) % 3 * 0.2:.1f}"])
    return rows


class RegularGridIsAHeatmap(unittest.TestCase):
    """A full two-parameter sweep (110 rows = 10 x 11) is a matrix, not a cloud."""

    def test_long_format_grid_becomes_heatmap(self):
        rec = _recommend(_long_grid())
        self.assertEqual(rec["recommended_figure_type"], "heatmap")
        plan = rec["figure_plan"]
        data = plan["data"] if "data" in plan else plan.get("payload", {})
        self.assertEqual(len(data["values"]), 10)
        self.assertEqual(len(data["values"][0]), 11)
        self.assertEqual(len(data["x_labels"]), 11)

    def test_scattered_rows_stay_scatter(self):
        rows = [["a", "b", "c"]] + [[str(i * 1.37), str((i * 7) % 13 + 0.5), str(i * 0.3)] for i in range(40)]
        self.assertEqual(_recommend(rows)["recommended_figure_type"], "scatter")

    def test_110_cell_heatmap_passes_the_density_check(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from report_workflow.nodes.figure_build import _dense_heatmap_issue

        fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
        data = {"values": [[1.0] * 11 for _ in range(10)]}
        ax.imshow(data["values"])
        fig.canvas.draw()
        self.assertIsNone(_dense_heatmap_issue(fig, ax, "F1", data))
        plt.close(fig)


class ChineseFirstLevelNumbering(unittest.TestCase):
    def test_zh_ordinals(self):
        from report_workflow.nodes.heading_contract_check import zh_ordinal

        got = [zh_ordinal(n) for n in (1, 9, 10, 11, 12, 20, 21, 99)]
        self.assertEqual(got, ["一", "九", "十", "十一", "十二", "二十", "二十一", "九十九"])

    def test_zh_document_headings_use_dun_numbering_and_are_idempotent(self):
        from report_workflow.nodes.heading_contract_check import normalize_heading_contract

        blueprint = {
            "section_order": ["intro", "method"],
            "sections": {
                "intro": {"title": "Introduction", "title_zh": "緒論", "required": True},
                "method": {"title": "Methods", "title_zh": "方法", "required": True},
            },
        }
        body = "這是一段用來判定文件語言的中文內容，說明研究背景與目的。" * 3
        md = ("\n\n").join(["# 1. 緒論", body, "## 1.1 背景", body, "# 2. 方法", body]) + "\n"
        once, issues = normalize_heading_contract(md, blueprint)
        self.assertEqual(issues, [])
        self.assertIn("# 一、緒論", once)
        self.assertIn("# 二、方法", once)
        self.assertNotIn("# 1. 緒論", once)
        self.assertEqual(normalize_heading_contract(once, blueprint)[0], once)


if __name__ == "__main__":
    unittest.main()
