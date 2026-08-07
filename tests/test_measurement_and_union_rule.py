"""Two ways a measurement lied, and the guards that stop them recurring.

The acceptance bar for this project is six numbers taken off a published DOCX.
Both faults here were found by running it, not by reading the code, and both are
the same class of mistake: a check that looked like it was working because the
thing it measured had quietly stopped being the thing it named.

* The body/source-list split was a regex pasted into a prompt, listing every
  heading except the one this pipeline emits. Three consecutive runs measured
  their own source list as analysis and reported 100% -- a threshold nothing can
  fail.
* The content gate counts a check as failed only when *no* cited evidence
  satisfied it. The counter incremented per finding rather than per evidence, so
  a claim stating the same figure twice failed the rule on the strength of one
  bad citation while another citation was stating that figure plainly.
"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from measure_report_body_density import measure, tail_headings  # noqa: E402
from report_workflow.nodes.citation_bind import (  # noqa: E402
    SOURCE_LIST_HEADING,
    SOURCE_LIST_HEADING_ZH,
)
from report_workflow.nodes.factuality_check import run_factuality_check_fe  # noqa: E402


def _docx(paragraphs: list[str]) -> str:
    """A minimal DOCX carrying one paragraph per string."""
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    xml = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    path = Path(tempfile.mkdtemp()) / "report.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return str(path)


class TheBodySplitFollowsTheHeadingTests(unittest.TestCase):
    def test_the_headings_the_pipeline_writes_are_the_ones_measured(self):
        # The whole fault was a hand-copied list that omitted 資料來源. Deriving
        # the set from the constants that emit it means a rename breaks this
        # test rather than silently restoring a 100% body share.
        headings = tail_headings()
        for constant in (SOURCE_LIST_HEADING, SOURCE_LIST_HEADING_ZH):
            self.assertIn(constant.lstrip("# ").strip(), headings)

    def test_the_source_list_is_not_counted_as_analysis(self):
        result = measure(_docx([
            "市場共 544 筆商品，中位價 71.99 美元。",
            "資料來源",
            "[S1] amazon_products.csv 第 12 行：4.09",
            "[S2] amazon_reviews.csv 第 77 行：18.18%",
        ]))
        self.assertEqual(result["tail_heading"], "資料來源")
        self.assertEqual(result["body_numbers"], 2)     # 544 and 71.99
        # 12, 4.09, 77, 18.18 — the digits in the [S1]/[S2] labels are
        # correctly not figures, being preceded by a word character.
        self.assertEqual(result["tail_numbers"], 4)
        self.assertLess(result["body_share"], 100.0)

    def test_an_authored_reference_heading_ends_the_body_too(self):
        result = measure(_docx([
            "Median price was 71.99.", "References", "[1] Example, 2026.",
        ]))
        self.assertEqual(result["tail_heading"], "References")
        self.assertEqual(result["body_numbers"], 1)

    def test_a_document_with_no_source_list_says_so(self):
        # Reported rather than passed off as a clean 100%: a missing heading and
        # an unrecognised heading give the same number and are not the same
        # thing.
        result = measure(_docx(["Median price was 71.99."]))
        self.assertIsNone(result["tail_heading"])
        self.assertEqual(result["body_share"], 100.0)

    def test_tables_and_drawings_are_counted_across_the_whole_document(self):
        path = _docx(["one"])
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("extra.xml", "")
        result = measure(path)
        self.assertEqual((result["tables"], result["figures"]), (0, 0))


class OneVotePerEvidenceTests(unittest.TestCase):
    """Citing two sources means the claim rests on their union."""

    STATES_IT = {
        "evidence_id": "has_it",
        "content": "評論數分布：0–10 則共 120 筆，10–50 則共 90 筆。",
        "block_type": "derived_statistic",
        "source_role": "source_data",
        "evidence_type": "quantitative",
        "allowed_claim_types": ["factual", "statistical"],
        "evidence_grade": "high",
    }
    DOES_NOT = {
        "evidence_id": "lacks_it",
        "content": "評論數的四分位為 3 筆、27 筆、198 筆。",
        "block_type": "derived_statistic",
        "source_role": "source_data",
        "evidence_type": "quantitative",
        "allowed_claim_types": ["factual", "statistical"],
        "evidence_grade": "high",
    }

    def _verdict(self, claim_text: str, evidence_ids: list[str]) -> dict:
        claim = {
            "claim_id": "c1",
            "claim_text": claim_text,
            "claim_type": "statistical",
            "evidence_ids": evidence_ids,
        }
        return run_factuality_check_fe(
            [{"claim_id": "c1", "status": "supported"}],
            {"claims": [claim]},
            [self.STATES_IT, self.DOES_NOT],
        )[0]

    def test_a_repeated_figure_no_longer_outvotes_the_citation_that_states_it(self):
        # 「10」 appears twice, naming two bands. Counted per finding, the one
        # failing citation contributed two votes and cleared the two-citation
        # threshold by itself -- so the claim was blocked while `has_it` stated
        # the figure outright.
        verdict = self._verdict(
            "評論數 0–10 則的商品有 120 筆，10–50 則有 90 筆。",
            ["has_it", "lacks_it"],
        )
        self.assertEqual(verdict["status"], "supported", verdict.get("reason", ""))

    def test_a_figure_no_cited_evidence_states_is_still_blocked(self):
        verdict = self._verdict(
            "評論數 0–10 則的商品有 777 筆，10–50 則有 777 筆。",
            ["has_it", "lacks_it"],
        )
        self.assertEqual(verdict["status"], "blocked")
        self.assertIn("777", verdict["reason"])

    def test_a_single_citation_behaves_exactly_as_before(self):
        self.assertEqual(
            self._verdict("評論數 0–10 則的商品有 120 筆。", ["lacks_it"])["status"],
            "blocked",
        )
        self.assertEqual(
            self._verdict("評論數 0–10 則的商品有 120 筆。", ["has_it"])["status"],
            "supported",
        )


if __name__ == "__main__":
    unittest.main()
