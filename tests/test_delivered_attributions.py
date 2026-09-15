"""What the reader sees in a citation, under a table, and in the closing appendix.

Found reading the delivered Word file of a Chinese course report, page by page.
First pass: the Sources list closed the document on three pages of raw JSON rows
and formula internals cut off mid-token; the table built from Knobloch et al.'s
data was attributed to "knobloch2020_table6_2015.csv (9 rows)"; one sentence
citing two undated U.S. DOE pages carried four parentheticals side by side.

Second pass, the reviewer's: the body mixed author-year citations with
``[S1]``–``[S24]``, the document ended on CSV file names and row counts listed
like sources, and a computed percentage was cited to the publication whose
figures it was computed from, as if that publication had stated it. A figure
the report computed now says so in the sentence — 本研究計算 — and points to an
appendix entry giving the formula, each input, and where each input came from;
no local file name stands where a source would.
"""
import json
import unittest
from datetime import datetime, timezone

from report_workflow.derived_evidence import build_requested_units
from report_workflow.nodes.citation_bind import (
    _format_source_trace_entry,
    merge_adjacent_trace_labels,
    resolve_citations_publication,
)
from report_workflow.nodes.source_tables import provenance_line
from report_workflow.source_citation import merge_adjacent_parentheticals

from tests.test_formula_derivations import REGISTRY, _cell

KNOBLOCH = {"author": "Knobloch, F., Hanssen, S. V., & Mercure, J.-F.", "year": "2020"}
CREATED_AT = datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat()

MAINTENANCE_ROW = {
    "evidence_id": "E_row_maint",
    "source_id": "p1",
    "source_file_name": "lca_parameters.csv",
    "file_type": "csv",
    "source_role": "primary_source",
    "block_type": "table_row",
    "content": json.dumps({"參數": "汽油車保養", "數值": "5", "單位": "g CO2e/km"}, ensure_ascii=False),
}


def _formula_units() -> list[dict]:
    units, problems = build_requested_units(
        [
            {"id": "battery_t", "op": "formula", "expr": "kwh * factor / 1000",
             "inputs": {"kwh": _cell("電池容量"), "factor": _cell("電池製造係數")},
             "unit": "t CO2e", "decimals": 3, "label": "電池製造排放"},
            {"id": "gap_t", "op": "formula", "expr": "body + battery - ice",
             "inputs": {"body": _cell("電動車車體製造"), "battery": "battery_t", "ice": _cell("汽油車車體製造")},
             "unit": "t CO2e", "decimals": 3, "label": "電動車多出的製造排放"},
        ],
        REGISTRY,
        CREATED_AT,
        zh=True,
    )
    assert problems == [], problems
    return units


SHEET_ROW = {
    **MAINTENANCE_ROW,
    "block_id": "block_1",
    "table_data": [["參數", "數值", "單位"], ["汽油車保養", "5", "g CO2e/km"]],
}


class InTextLabelTests(unittest.TestCase):
    """A label sends the reader where the figure can be checked.

    The second revision of the course report: every label pointed at an entry
    of a generated appendix — "（本研究計算，附錄 A8）" — and the appendix was
    pages of program variables, 0/1 switches and the same parameters repeated
    under every formula. A figure a table prints now points at the table, one
    the report's own appendix explains points there, and only a figure with
    neither points at its entry in the separate calculation record.
    """

    def test_a_figure_with_no_table_or_explanation_points_at_its_record_entry(self):
        units = _formula_units()
        resolved, _audit, _refs, _internal, entries = resolve_citations_publication(
            "電動車多排約 3.572 t CO2e [CITE:E_D_gap_t]。", units, []
        )
        self.assertIn("電動車多排約 3.572 t CO2e（本研究計算，計算附件 C1）。", resolved)
        self.assertNotIn("[S", resolved)

    def test_a_figure_in_a_placed_table_points_at_the_table(self):
        units, problems = build_requested_units(
            [{"id": "use", "op": "formula", "source": "scenarios.csv", "row_label": "情境", "decimals": 1,
              "formulas": [{"label": "電動車", "expr": "grid * 0.2", "unit": "g CO2e/km"}]}],
            REGISTRY, CREATED_AT, zh=True,
        )
        self.assertEqual(problems, [])
        pointers: dict[str, str] = {}
        resolved, *_rest = resolve_citations_publication(
            "[TABLE:gap_t 其他表]\n\n[TABLE:use 各情境]\n\n電動車為 121.2 g CO2e/km [CITE:E_D_use]。",
            units, [], table_evidence_ids=["E_D_use"], table_pointers=pointers,
        )
        self.assertIn("電動車為 121.2 g CO2e/km（本研究計算，表 1）。", resolved)
        # The table's own attribution cannot point at itself.
        self.assertEqual(pointers, {"E_D_use": "計算附件 C1"})

    def test_a_figure_the_report_explains_points_at_the_explanation(self):
        units, problems = build_requested_units(
            [{"id": "battery_t", "op": "formula", "expr": "kwh * factor / 1000", "unit": "t CO2e", "decimals": 3,
              "inputs": {"kwh": _cell("電池容量"), "factor": _cell("電池製造係數")},
              "label": "電池製造排放", "explained_in": "附錄 A.3"}],
            REGISTRY, CREATED_AT, zh=True,
        )
        self.assertEqual(problems, [])
        resolved, *_rest = resolve_citations_publication("電池排放 4.272 t CO2e [CITE:E_D_battery_t]。", units, [])
        self.assertIn("電池排放 4.272 t CO2e（本研究計算，附錄 A.3）。", resolved)

    def test_a_row_of_the_authors_sheet_is_compiled_not_a_source(self):
        resolved, _audit, _refs, _internal, entries = resolve_citations_publication(
            "汽油車保養排放為 5 g CO2e/km [CITE:E_row_maint]。", [MAINTENANCE_ROW], []
        )
        self.assertIn("（本研究整理，計算附件 C1）", resolved)
        self.assertEqual(entries, ["**C1**　參數：汽油車保養；數值：5；單位：g CO2e/km（本研究整理）"])

    def test_a_row_of_a_sheet_the_report_prints_points_at_that_table(self):
        resolved, *_rest = resolve_citations_publication(
            "[TABLE:lca_parameters 參數]\n\n汽油車保養排放為 5 g CO2e/km [CITE:E_row_maint]。", [SHEET_ROW], []
        )
        self.assertIn("汽油車保養排放為 5 g CO2e/km（本研究整理，表 1）。", resolved)

    def test_a_figure_computed_from_a_publication_names_both(self):
        derived = {
            "evidence_id": "E_D_gap",
            "source_id": "k1",
            "source_file_name": "knobloch2020_table6_2015.csv",
            "block_type": "derived_statistic",
            "citation": KNOBLOCH,
            "content": "衍生計算(來源:knobloch2020_table6_2015.csv):2015 年各地區相對變化。",
            "derivation": {"method": "formula_table", "formulas": [{"label": "相對變化 (%)", "expression": "(ev - gas) / gas * 100"}]},
        }
        resolved, *_rest = resolve_citations_publication("波蘭為 +14.5% [CITE:E_D_gap]。", [derived], [])
        self.assertIn("波蘭為 +14.5%（Knobloch et al., 2020；本研究計算，計算附件 C1）。", resolved)
        english, *_rest = resolve_citations_publication("Poland is +14.5% [CITE:E_D_gap].", [derived], [])
        self.assertIn("(Knobloch et al., 2020; calculated in this study, calculation record C1)", english)

    def test_adjacent_labels_merge_into_one_parenthetical(self):
        text = "約 32,800 km（本研究計算，表 6）（本研究計算，附錄 A.4）；（本研究整理，計算附件 C3）。"
        self.assertEqual(
            merge_adjacent_trace_labels(text),
            "約 32,800 km（本研究計算，表 6、附錄 A.4；本研究整理，計算附件 C3）。",
        )

    def test_merged_places_read_in_order_without_a_repeated_prefix(self):
        # The report printed "（本研究計算，附錄 A.4、附錄 A.3）".
        self.assertEqual(
            merge_adjacent_trace_labels("排放（本研究計算，附錄 A.4）（本研究計算，附錄 A.3、A.4）（本研究計算，表 6）（本研究計算，表 5）。"),
            "排放（本研究計算，附錄 A.3、A.4、表 5、表 6）。",
        )

    def test_a_publication_and_a_label_side_by_side_share_one_bracket(self):
        # Three brackets in a row — "（本研究計算，附錄 A.2）（環境部氣候變遷署，2025d） (Ember, 2026)" —
        # read as three citation systems in one sentence.
        self.assertEqual(
            merge_adjacent_trace_labels("658.4 g CO2e/kWh（本研究計算，附錄 A.2）（環境部氣候變遷署，2025d） (Ember, 2026)。"),
            "658.4 g CO2e/kWh（環境部氣候變遷署，2025d；Ember, 2026；本研究計算，附錄 A.2）。",
        )
        self.assertEqual(
            merge_adjacent_trace_labels("4 g CO2e/km (Negri & Bieker, 2025)（本研究整理，計算附件 C1、C2、C3）。"),
            "4 g CO2e/km（Negri & Bieker, 2025；本研究整理，計算附件 C1–C3）。",
        )
        self.assertEqual(
            merge_adjacent_trace_labels("is 4 g (Negri & Bieker, 2025) (compiled in this study, calculation record C2)."),
            "is 4 g (Negri & Bieker, 2025; compiled in this study, calculation record C2).",
        )

    def test_publications_alone_are_left_to_the_author_year_merge(self):
        text = "低 73% (Negri & Bieker, 2025)（國家發展委員會，2022）。"
        self.assertEqual(merge_adjacent_trace_labels(text), text)


class AppendixEntryTests(unittest.TestCase):
    def test_an_entry_gives_the_formula_and_each_input_without_a_file_name(self):
        units = _formula_units()
        battery = next(unit for unit in units if unit["evidence_id"] == "E_D_battery_t")
        entry = _format_source_trace_entry(battery, 1, "zh")
        self.assertTrue(entry.startswith("**C1**　電池製造排放為 4.272 t CO2e（本研究計算）。"), entry)
        # Written for a reader, not a parser: × and ÷, and each input as its
        # value, its unit and the row it was read from — not every column.
        self.assertIn("計算式：kwh × factor ÷ 1000", entry)
        self.assertIn("kwh = 53.4 kWh（電池容量）", entry)
        self.assertNotIn("lca_parameters.csv", entry)

    def test_an_input_names_its_source_column_when_the_sheet_has_one(self):
        from report_workflow.nodes.citation_bind import _operand_notes

        notes, _names = _operand_notes({
            "kwh": {"source_file": "p.csv", "row_filter": "參數=電池容量", "column": "數值", "value": 53.4,
                    "fields": {"參數": "電池容量", "數值": "53.4", "單位": "kWh", "資料年份": "2023",
                               "來源": "Negri & Bieker (2025)", "說明": "歐盟 2023 年售出中型電動車平均"}},
        }, True, None)
        self.assertEqual(notes, ["kwh = 53.4 kWh（電池容量；Negri & Bieker (2025)）"])

    def test_an_input_from_a_wide_sheet_names_its_unit_and_the_publication(self):
        # A vehicle sheet carries its units in the column headers and its source
        # as a declared publication, and the record printed "ice_fc = 6.9（汽油車）".
        from report_workflow.nodes.citation_bind import _operand_notes

        notes, _names = _operand_notes({
            "ice_fc": {"source_file": "vehicles.csv", "row_filter": "車種=汽油車", "column": "實際油耗 (L/100 km)",
                       "value": 6.9, "fields": {"車種": "汽油車", "實際油耗 (L/100 km)": "6.9"},
                       "citation": {"author": "Negri, M., & Bieker, G.", "year": "2025"}},
        }, True, None)
        self.assertEqual(notes, ["ice_fc = 6.9 L/100 km（汽油車 實際油耗；Negri & Bieker (2025)）"])

    def test_a_per_row_input_read_from_an_earlier_table_points_at_that_table(self):
        units, problems = build_requested_units(
            [
                {"id": "factors", "op": "formula", "source": "scenarios.csv", "row_label": "情境", "decimals": 4,
                 "formulas": [{"label": "電力係數", "expr": "grid", "unit": "g CO2e/kWh"}]},
                {"id": "use", "op": "formula", "source": "scenarios.csv", "row_label": "情境", "decimals": 1,
                 "formulas": [{"label": "電動車", "expr": "ec / 100 * g", "unit": "g CO2e/km"}],
                 "inputs": {"ec": {"source": "lca_parameters.csv", "rows": "參數=電池容量", "column": "數值"},
                            "g": {"table": "factors", "column": "電力係數 (g CO2e/kWh)"}}},
            ],
            REGISTRY, CREATED_AT, zh=True,
        )
        self.assertEqual(problems, [])
        _resolved, _audit, _refs, _internal, entries = resolve_citations_publication(
            "電動車為 250 g CO2e/km [CITE:E_D_use]。", units, []
        )
        self.assertIn("g 取 C2 表中各列的 電力係數 (g CO2e/kWh)", entries[0])
        self.assertTrue(entries[1].startswith("**C2**"), entries)

    def test_a_figure_computed_from_a_declared_publication_names_it_in_its_entry(self):
        entry = _format_source_trace_entry({
            "source_file_name": "knobloch.csv", "block_type": "derived_statistic", "citation": KNOBLOCH,
            "content": "衍生計算(來源:knobloch.csv):2015 年各地區相對變化。",
            "derivation": {"method": "formula_table", "operands": {},
                           "row_inputs": {"ev": {"column": "電動車中位數 (g CO2e/km)"}},
                           "formulas": [{"label": "相對變化 (%)", "expression": "(ev / gas - 1) * 100"}]},
        }, 15, "zh")
        self.assertIn("資料出處：Knobloch et al. (2020)", entry)
        self.assertIn("ev 取各列的 電動車中位數 (g CO2e/km)", entry)

    def test_per_row_inputs_are_listed_in_the_order_the_formula_uses_them(self):
        entry = _format_source_trace_entry({
            "source_file_name": "s.csv", "block_type": "derived_statistic",
            "content": "衍生計算(來源:s.csv):情境排放。",
            "derivation": {"method": "formula_table", "operands": {},
                           "formulas": [{"label": "電動車", "expression": "用碳足跡 * g + 用歐盟電網 * e + 汽油含上游"}]},
        }, 3, "zh")
        self.assertIn("各列輸入：用碳足跡、g、用歐盟電網、e、汽油含上游", entry)

    def test_a_per_row_input_from_the_table_own_sheet_is_given_row_by_row(self):
        # 附錄 A8 read "各列輸入：用排碳係數、用碳足跡、…" and never said what
        # any scenario took, so its table could not be redone from the appendix.
        units, problems = build_requested_units(
            [{"id": "use", "op": "formula", "source": "scenarios.csv", "row_label": "情境", "decimals": 1,
              "formulas": [{"label": "電動車", "expr": "ec / 100 * grid", "unit": "g CO2e/km"}],
              "inputs": {"ec": _cell("電池容量")}}],
            REGISTRY, CREATED_AT, zh=True,
        )
        self.assertEqual(problems, [])
        use = next(unit for unit in units if unit["evidence_id"] == "E_D_use")
        entry = _format_source_trace_entry(use, 8, "zh")
        self.assertIn("各列輸入（各列依序為 A、B）：grid 467、605.8", entry)

    def test_an_input_that_only_repeats_the_row_labels_is_not_listed_twice(self):
        # "各列依序為 0、50、…、800：電網碳強度 0、50、…、800" — the label
        # column was 標籤, a copy of the input column under another name.
        for label_column in ("電網碳強度", "標籤"):
            with self.subTest(label_column=label_column):
                entry = _format_source_trace_entry({
                    "source_file_name": "grid_points.csv", "block_type": "derived_statistic",
                    "content": "衍生計算(來源:grid_points.csv):碳平衡點。",
                    "table_grid": {"headers": ["電網碳強度 (g CO2e/kWh)", "碳平衡點 (km)"],
                                   "rows": [["0", "17,581"], ["1000", "120,000"]]},
                    "derivation": {"method": "formula_table", "operands": {}, "row_label": label_column,
                                   "row_values": {"電網碳強度": ["0", "1,000"]},
                                   "formulas": [{"label": "碳平衡點 (km)", "expression": "17581 + 102.4 * 電網碳強度"}]},
                }, 22, "zh")
                self.assertIn("各列輸入：電網碳強度。", entry)

    def test_an_input_computed_earlier_gets_its_own_entry_and_a_pointer_to_it(self):
        units = _formula_units()
        _resolved, _audit, _refs, _internal, entries = resolve_citations_publication(
            "多排 3.572 t CO2e [CITE:E_D_gap_t]。", units, []
        )
        self.assertEqual(len(entries), 2, entries)
        self.assertIn("battery = 4.272（C2）", entries[0])
        self.assertTrue(entries[1].startswith("**C2**　電池製造排放為 4.272 t CO2e"), entries[1])

    def test_a_placed_table_is_numbered_after_the_figures_the_text_cites(self):
        units = _formula_units()
        numbers: dict[str, int] = {}
        _resolved, _audit, _refs, _internal, entries = resolve_citations_publication(
            "電池排放 4.272 t CO2e [CITE:E_D_battery_t]。", units, [],
            table_evidence_ids=["E_D_gap_t"], entry_numbers=numbers,
        )
        self.assertEqual(numbers, {"E_D_battery_t": 1, "E_D_gap_t": 2})
        self.assertEqual(len(entries), 2)

    def test_a_document_excerpt_keeps_its_locator(self):
        entry = _format_source_trace_entry(
            {"source_file_name": "notes.md", "source_span": "lines 4-9", "content": "回收率可達 95%"}, 2, "zh"
        )
        self.assertEqual(entry, "**C2**　“回收率可達 95%”（本研究整理自 notes.md lines 4-9）")

    def test_a_long_quote_is_cut_at_a_boundary_not_inside_a_word(self):
        prose = "，".join(f"第{index}段說明電池回收的條件與限制" for index in range(20))
        entry = _format_source_trace_entry({"source_file_name": "notes.md", "content": prose}, 2, "zh")
        self.assertIn("限制…”（本研究整理自 notes.md）", entry)


class TableProvenanceTests(unittest.TestCase):
    def test_a_table_over_a_declared_publication_names_the_publication_and_the_calculation(self):
        table = {"source_file_name": "knobloch2020_table6_2015.csv", "source_span": "knobloch2020_table6_2015.csv (9 rows)",
                 "computed": True, "citation": KNOBLOCH}
        self.assertEqual(provenance_line(table, "zh", "附錄 A.1"), "來源：Knobloch et al. (2020)，本研究計算（附錄 A.1）")
        self.assertEqual(provenance_line(table, "en", "calculation record C1"),
                         "Source: Knobloch et al. (2020); calculated in this study (calculation record C1)")

    def test_a_computed_table_names_no_file(self):
        table = {"source_file_name": "scenarios.csv", "source_span": "scenarios.csv (5 rows)", "computed": True}
        self.assertEqual(provenance_line(table, "zh", "計算附件 C3"), "來源：本研究計算（計算附件 C3）")
        self.assertEqual(provenance_line(table, "zh"), "來源：本研究計算")

    def test_the_authors_own_sheet_is_compiled(self):
        table = {"source_file_name": "lca_parameters.csv", "source_span": "", "file_type": "csv"}
        self.assertEqual(provenance_line(table, "zh"), "來源：本研究整理")
        self.assertEqual(provenance_line(table, "en"), "Source: compiled in this study")

    def test_a_table_from_a_document_keeps_its_locator(self):
        table = {"source_file_name": "report.pdf", "source_span": "page 3", "file_type": "pdf"}
        self.assertEqual(provenance_line(table, "zh"), "來源：report.pdf page 3")


class UndatedCitationTests(unittest.TestCase):
    def test_suffixed_undated_citations_merge_like_dated_ones(self):
        text = "能量只有約 12%–30% (U.S. DOE & U.S. EPA, n.d.-a) (U.S. DOE & U.S. EPA, n.d.-a) (U.S. DOE & U.S. EPA, n.d.-b)。"
        self.assertEqual(
            merge_adjacent_parentheticals(text),
            "能量只有約 12%–30% (U.S. DOE & U.S. EPA, n.d.-a; U.S. DOE & U.S. EPA, n.d.-b)。",
        )


if __name__ == "__main__":
    unittest.main()
