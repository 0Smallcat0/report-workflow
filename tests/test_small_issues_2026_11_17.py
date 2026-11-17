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


if __name__ == "__main__":
    unittest.main()
