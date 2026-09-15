"""A PDF whose tables have a merged cell is a normal PDF.

pdfplumber reports merged and blank cells as None; the block model holds
strings. Preparing a run from the ICCT white paper stopped at SOURCE_PARSE
with "110 validation errors for SourceContentBlock" — a hundred lines naming
table_data.0.1, table_data.0.3, ... and neither the file nor the page.
"""
import sys
import types
import unittest
from unittest.mock import patch

from report_workflow.errors import QAHardBlockError
from report_workflow.nodes import source_parse
from report_workflow.parsers.semi_structured_parser import parse_pdf
from report_workflow.state import ReportState, SourceContentBlock


class _Page:
    def extract_text(self):
        return "Table 2 Battery production emissions intensity by region"

    def extract_tables(self):
        return [[["kg CO2e/kWh", None, "Europe"], ["NMC622", None, "60"], None]]


class _Pdf:
    pages = [_Page()]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MergedCellTests(unittest.TestCase):
    def test_a_merged_cell_becomes_an_empty_string(self):
        fake = types.SimpleNamespace(open=lambda path: _Pdf())
        with patch.dict(sys.modules, {"pdfplumber": fake}):
            result = parse_pdf("paper.pdf")
        self.assertTrue(result["success"], result.get("error"))
        table = next(block for block in result["blocks"] if block["block_type"] == "table")
        self.assertEqual(table["table_data"], [["kg CO2e/kWh", "", "Europe"], ["NMC622", "", "60"]])
        SourceContentBlock(**table)  # the model accepts what the parser returns

    def test_a_block_the_model_refuses_is_reported_by_file_and_page(self):
        state = ReportState.new("probe", ["paper.pdf"], None)
        state.sources["source_registry"] = [{
            "source_id": "s1", "file_name": "paper.pdf", "file_path": "paper.pdf",
            "file_type": "pdf", "artifact_role": "source_data",
        }]
        broken = {"blocks": [{"block_id": "page_7_table_0", "block_type": "table", "content": "x y z",
                              "page_number": 7, "table_data": [[None, 3]]}], "success": True}
        with patch.object(source_parse, "parse_single_source", return_value=broken), \
                patch.object(source_parse, "validate_parsed_output", return_value=(True, "")):
            with self.assertRaises(QAHardBlockError) as caught:
                source_parse.run_source_parse(state)
        message = str(caught.exception)
        self.assertIn("paper.pdf", message)
        self.assertIn("page 7", message)
        self.assertLess(len(message), 400)


if __name__ == "__main__":
    unittest.main()
