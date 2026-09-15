"""A line chart can mark the point its argument is about.

Found revising a Chinese LCA course report: the cumulative-emissions chart is
drawn to show where the electric car's line crosses the petrol car's and the
hybrid's, and the reviewer asked for those two break-even points to be marked.
A line chart placed its series at the index of each label, so a crossing at
44,208.8 km — between the 40,000 and 60,000 ticks — had no position to be
drawn at, and there was no way to say "mark this". The chart now takes numeric
x positions and labelled markers, and a marker is a plotted value like any
other: the evidence the figure cites has to state it.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from report_workflow.nodes import figure_build
from report_workflow.nodes.figure_plan_audit import _plotted_numbers, _value_support_issues

DATA = {
    "labels": ["0", "20,000", "40,000", "60,000"],
    "x": [0, 20000, 40000, 60000],
    "series": [
        {"name": "汽油車", "values": [7.2, 11.3, 15.5, 19.6]},
        {"name": "電動車", "values": [10.8, 13.3, 15.8, 18.4]},
    ],
    "markers": [{"x": 44208.8, "label": "對汽油車碳平衡點 約 44,200 km"}],
}


class LineMarkerTests(unittest.TestCase):
    def test_series_sit_at_their_x_and_the_marker_is_drawn_with_its_label(self):
        captured = {}

        def capture(fig, ax, figure_id, figure_type, data, output_path, dpi):
            captured["texts"] = [text.get_text() for text in ax.texts]
            captured["xdata"] = [list(line.get_xdata()) for line in ax.lines]
            return []

        with TemporaryDirectory() as tmp, patch.object(figure_build, "_save_figure", capture):
            figure_build._generate_line(
                "3", "累積排放", DATA, "累積行駛里程 (km)", "累積排放 (t CO2e)",
                6, 4, 100, Path(tmp) / "3.png",
            )
        self.assertIn([0, 20000, 40000, 60000], captured["xdata"])
        self.assertIn("對汽油車碳平衡點 約 44,200 km", captured["texts"])
        self.assertTrue(
            any(xs and all(abs(x - 44208.8) < 1e-6 for x in xs) for xs in captured["xdata"]),
            "no vertical line at the marker",
        )

    def test_a_marker_label_is_not_crossed_by_the_next_marker_line(self):
        # The delivered chart marked 44,200 km and 105,300 km; the first
        # label ran past 105,300 and its dashed line cut through "44,2|00 km".
        captured = {}

        def capture(fig, ax, figure_id, figure_type, data, output_path, dpi):
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            captured["labels"] = [(text, text.get_window_extent(renderer=renderer)) for text in ax.texts]
            captured["lines"] = [
                (line, ax.transData.transform((line.get_xdata()[0], 0))[0])
                for line in ax.lines if line.get_linestyle() == "--"
            ]
            return []

        data = {
            "labels": ["0", "80,000", "160,000", "240,000"],
            "x": [0, 80000, 160000, 240000],
            "series": [{"name": "汽油車", "values": [7.2, 23.8, 40.3, 56.9]}],
            "markers": [
                {"x": 44208.8, "label": "對汽油車碳平衡點 約 44,200 km"},
                {"x": 105311.6, "label": "對油電混合車碳平衡點 約 105,300 km"},
            ],
        }
        with TemporaryDirectory() as tmp, patch.object(figure_build, "_save_figure", capture):
            figure_build._generate_line("3", "累積排放", data, "累積行駛里程 (km)", "累積排放 (t CO2e)", 6, 4, 100, Path(tmp) / "3.png")
        crossings = [
            (text, line) for text, extent in captured["labels"] for line, line_x in captured["lines"]
            if extent.x0 < line_x < extent.x1
        ]
        self.assertTrue(crossings, "the case no longer puts a label across a line")
        for text, line in crossings:
            patch_ = text.get_bbox_patch()
            self.assertIsNotNone(patch_, f"{text.get_text()!r} is printed straight over a dashed line")
            self.assertEqual(patch_.get_facecolor()[3], 1.0)
            self.assertGreater(text.get_zorder(), line.get_zorder())

    def test_a_distance_in_kilometres_reads_with_thousands_separators(self):
        # A break-even axis in km printed "120000" beside prose writing
        # "119,300 km"; the axis should read the way the sentence does.
        captured = {}

        def capture(fig, ax, figure_id, figure_type, data, output_path, dpi):
            fig.canvas.draw()
            captured["yticks"] = [label.get_text() for label in ax.get_yticklabels()]
            return []

        data = {"labels": ["0", "400", "800"], "series": [{"name": "電池 80", "values": [17581, 29190, 85927]}]}
        with TemporaryDirectory() as tmp, patch.object(figure_build, "_save_figure", capture):
            figure_build._generate_line("4", "碳平衡點", data, "電網碳強度", "碳平衡點 (km)", 6, 4, 100, Path(tmp) / "4.png")
        self.assertTrue(any("," in label for label in captured["yticks"]), captured["yticks"])

    def test_a_marker_is_a_plotted_value(self):
        self.assertIn(44208.8, _plotted_numbers(DATA))

    def test_a_marker_the_evidence_does_not_state_is_refused(self):
        figure = {"figure_id": "3", "source_evidence_ids": ["E_curve"], "data": DATA}
        ledger = {"E_curve": {"evidence_id": "E_curve", "content": "0 7.2 10.8 20000 11.3 13.3 40000 15.5 15.8 60000 19.6 18.4"}}
        issues = _value_support_issues(figure, 0, ledger, None)
        self.assertEqual(len(issues), 1)
        self.assertIn(44208.8, issues[0]["unsupported_values"])

        ledger["E_breakeven"] = {"evidence_id": "E_breakeven", "content": "碳平衡點 44,208.8 km"}
        figure["source_evidence_ids"] = ["E_curve", "E_breakeven"]
        self.assertEqual(_value_support_issues(figure, 0, ledger, None), [])


if __name__ == "__main__":
    unittest.main()
