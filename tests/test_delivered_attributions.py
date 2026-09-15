"""What the reader sees under a table, in the Sources list and in a citation.

Found reading the delivered Word file of a Chinese course report, page by page:
the Sources list closed the document on three pages of raw JSON rows and of
formula internals cut off mid-token; the table built from Knobloch et al.'s data
was attributed to "knobloch2020_table6_2015.csv (9 rows)"; and one sentence
citing two undated U.S. DOE pages carried four parentheticals side by side.
"""
import json
import unittest

from report_workflow.nodes.citation_bind import _format_source_trace_entry
from report_workflow.nodes.source_tables import provenance_line
from report_workflow.source_citation import merge_adjacent_parentheticals

KNOBLOCH = {"author": "Knobloch, F., Hanssen, S. V., & Mercure, J.-F.", "year": "2020"}


class SourceListTests(unittest.TestCase):
    def test_a_data_row_is_listed_as_its_fields(self):
        line = _format_source_trace_entry({
            "source_file_name": "lca_parameters.csv",
            "block_type": "csv_row",
            "content": json.dumps({"參數": "汽油車保養", "數值": "5", "單位": "g CO2e/km"}, ensure_ascii=False),
        }, 1)
        self.assertEqual(line, "[S1] lca_parameters.csv — 參數：汽油車保養；數值：5；單位：g CO2e/km")

    def test_a_computed_figure_is_listed_as_its_result_marked_computed(self):
        line = _format_source_trace_entry({
            "source_file_name": "lca_parameters.csv",
            "source_span": "lca_parameters.csv (6 rows)",
            "block_type": "derived_statistic",
            "content": "衍生計算(來源:lca_parameters.csv):車用汽油只算燃燒的排放係數為 2.2906 kg CO2e/L。"
                       "計算式:heat * 4.1868e-9 * (co2 + ch4 * gwp_ch4)；其中 heat = 7,586（lca_parameters.csv 中 參數=熱值 的 數值）。",
        }, 4)
        self.assertEqual(line, "[S4] lca_parameters.csv (6 rows) — 本報告計算：車用汽油只算燃燒的排放係數為 2.2906 kg CO2e/L")
        self.assertNotIn("heat", line)

    def test_a_long_quote_is_cut_at_a_boundary_not_inside_a_word(self):
        prose = "，".join(f"第{index}段說明電池回收的條件與限制" for index in range(20))
        line = _format_source_trace_entry({"source_file_name": "notes.md", "content": prose}, 2)
        self.assertTrue(line.endswith("限制…”"), line)


class TableProvenanceTests(unittest.TestCase):
    def test_a_table_over_a_declared_publication_names_the_publication(self):
        table = {"source_file_name": "knobloch2020_table6_2015.csv", "source_span": "knobloch2020_table6_2015.csv (9 rows)",
                 "computed": True, "citation": KNOBLOCH}
        self.assertEqual(provenance_line(table, "zh"), "來源：Knobloch et al. (2020)，本報告整理計算")
        self.assertEqual(provenance_line(table, "en"), "Source: Knobloch et al. (2020); computed for this report")

    def test_a_computed_table_says_it_was_computed(self):
        table = {"source_file_name": "scenarios.csv", "source_span": "scenarios.csv (5 rows)", "computed": True}
        self.assertEqual(provenance_line(table, "zh"), "來源：scenarios.csv (5 rows)，本報告計算")


class UndatedCitationTests(unittest.TestCase):
    def test_suffixed_undated_citations_merge_like_dated_ones(self):
        text = "能量只有約 12%–30% (U.S. DOE & U.S. EPA, n.d.-a) (U.S. DOE & U.S. EPA, n.d.-a) (U.S. DOE & U.S. EPA, n.d.-b)。"
        self.assertEqual(
            merge_adjacent_parentheticals(text),
            "能量只有約 12%–30% (U.S. DOE & U.S. EPA, n.d.-a; U.S. DOE & U.S. EPA, n.d.-b)。",
        )


if __name__ == "__main__":
    unittest.main()
