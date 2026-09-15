"""A parameter sheet can be placed in the document as the table it is.

Found revising a Chinese LCA course report: the reviewer asked for a parameter
table — value, unit, data year, source, scope — and the sheet holding exactly
those columns was already one of the sources. ``[TABLE:]`` placed tables found
inside documents and tables the pipeline computed, but a CSV's rows carry
``block_<n>`` ids with no parent table, so the one table the author had built
for the reader was the one that could not be placed, and the only way left was
to retype its numbers into the draft where nothing checks them.
"""
import json
import unittest

from report_workflow.nodes.source_tables import collect_source_tables, replace_table_placeholders

HEADERS = ["參數", "數值", "單位", "來源"]
ROWS = [
    ["汽油車實際油耗", "6.9", "L/100 km", "Negri & Bieker (2025)"],
    ["電動車實際電耗", "20.2", "kWh/100 km", "Negri & Bieker (2025)"],
    ["使用年限", "15", "年", "本研究假設"],
]


def _csv_row(index: int, values: list[str], file_name: str = "lca_parameters.csv") -> dict:
    return {
        "evidence_id": f"E_p_{index}",
        "source_file_name": file_name,
        "file_type": "csv",
        "block_id": f"block_{index}",
        "block_type": "table_row",
        "content": json.dumps(dict(zip(HEADERS, values)), ensure_ascii=False),
        "table_data": [HEADERS, values],
    }


class StructuredSourceTableTests(unittest.TestCase):
    def test_a_csv_is_placeable_under_its_file_stem_in_source_order(self):
        ledger = [_csv_row(2, ROWS[2]), _csv_row(0, ROWS[0]), _csv_row(1, ROWS[1])]
        tables = collect_source_tables(ledger)
        self.assertIn("lca_parameters", tables)
        table = tables["lca_parameters"]
        self.assertEqual(table["headers"], HEADERS)
        self.assertEqual([row[0] for row in table["rows"]], ["汽油車實際油耗", "電動車實際電耗", "使用年限"])
        self.assertEqual(table["evidence_ids"], ["E_p_0", "E_p_1", "E_p_2"])

    def test_the_marker_renders_every_row(self):
        ledger = [_csv_row(index, values) for index, values in enumerate(ROWS)]
        markdown, placed, unresolved = replace_table_placeholders(
            "本研究採用的參數如下。\n\n[TABLE:lca_parameters 本研究採用的參數]\n", ledger
        )
        self.assertEqual((placed, unresolved), (1, []))
        self.assertIn("表 1. 本研究採用的參數", markdown)
        self.assertIn("| 使用年限 | 15 | 年 | 本研究假設 |", markdown)

    def test_a_row_from_a_document_is_not_mistaken_for_a_sheet(self):
        note = {
            "evidence_id": "E_note",
            "source_file_name": "notes.md",
            "file_type": "md",
            "block_id": "block_0",
            "block_type": "table_row",
            "content": "筆記",
            "table_data": [["a"], ["b"]],
        }
        self.assertNotIn("notes", collect_source_tables([note]))


if __name__ == "__main__":
    unittest.main()
