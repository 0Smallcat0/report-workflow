"""Contract tests for the zero-schema ``verify()`` adapter.

``report_workflow.verify`` is the adoption surface: a plain answer string plus
plain source texts, no claim matrix, no sentence map. These tests pin its
sentence splitting, citation-marker scoping, any-single-source grounding
semantics, fail-closed behavior, and determinism.
"""
import unittest

from report_workflow import verify

SRC_ERROR = (
    "The error rate fell to 3.5% under the structured workflow, "
    "down from 9.0% for the manual baseline."
)
SRC_TIME = (
    "Median processing time was 12.4 minutes for the manual baseline "
    "and 7.8 minutes for the structured workflow."
)
SRC_ZH = "結構化流程將中位處理時間從12.4分鐘,降至7.8分鐘;錯誤率降至3.5%。"


class VerifyAdapterTests(unittest.TestCase):
    def test_honest_answer_is_publishable(self):
        result = verify(
            "The structured workflow cut the median processing time to 7.8 minutes.",
            SRC_TIME,
        )
        self.assertTrue(result["publishable"])
        self.assertEqual(result["verified_count"], 1)
        self.assertEqual(result["blocked_count"], 0)
        row = result["sentence_results"][0]
        self.assertEqual(row["status"], "verified")
        self.assertEqual(row["source_id"], "1")

    def test_invented_number_is_blocked_by_fe(self):
        result = verify("The error rate fell to 0.2%.", SRC_ERROR)
        row = result["sentence_results"][0]
        self.assertFalse(result["publishable"])
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["checker"], "FE")
        self.assertIn("0.2", row["reason"])

    def test_precision_inflation_is_blocked(self):
        result = verify("The error rate fell to 3.53%.", SRC_ERROR)
        row = result["sentence_results"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["checker"], "FE")
        self.assertIn("precision", row["reason"])

    def test_unknown_citation_marker_is_blocked_by_fa(self):
        result = verify("An external audit certified the results [9].", {"1": SRC_ERROR})
        row = result["sentence_results"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["checker"], "FA")
        self.assertIn("unknown source id", row["reason"])
        self.assertIn("9", row["reason"])

    def test_marker_scopes_sentence_to_cited_source(self):
        # The number 7.8 minutes exists only in SRC_TIME; citing SRC_ERROR
        # explicitly must block instead of silently falling back to SRC_TIME.
        result = verify(
            "Processing time fell to 7.8 minutes [err].",
            {"err": SRC_ERROR, "time": SRC_TIME},
        )
        self.assertEqual(result["sentence_results"][0]["status"], "blocked")

    def test_cite_syntax_marker_is_accepted(self):
        result = verify(
            "Processing time fell to 7.8 minutes [CITE:time].",
            {"err": SRC_ERROR, "time": SRC_TIME},
        )
        row = result["sentence_results"][0]
        self.assertEqual(row["status"], "verified")
        self.assertEqual(row["source_id"], "time")

    def test_unmarked_sentence_grounds_in_any_single_source(self):
        result = verify(
            "The error rate fell to 3.5%. Processing time fell to 7.8 minutes.",
            {"a": SRC_TIME, "b": SRC_ERROR},
        )
        rows = result["sentence_results"]
        self.assertEqual([row["status"] for row in rows], ["verified", "verified"])
        self.assertEqual(rows[0]["source_id"], "b")
        self.assertEqual(rows[1]["source_id"], "a")

    def test_ungrounded_sentence_blocks_against_all_sources(self):
        result = verify(
            "The pilot won a national innovation award.",
            {"a": SRC_TIME, "b": SRC_ERROR},
        )
        row = result["sentence_results"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["checker"], "FE")
        self.assertIsNone(row["source_id"])

    def test_list_sources_are_auto_numbered(self):
        result = verify("The error rate fell to 3.5% [2].", [SRC_TIME, SRC_ERROR])
        row = result["sentence_results"][0]
        self.assertEqual(row["status"], "verified")
        self.assertEqual(row["source_id"], "2")

    def test_cjk_sentences_split_and_verify(self):
        result = verify("結構化流程將中位處理時間降至7.8分鐘。錯誤率降至0.9%。", SRC_ZH)
        rows = result["sentence_results"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "verified")
        self.assertEqual(rows[1]["status"], "blocked")
        self.assertFalse(result["publishable"])

    def test_cross_language_answer_fails_closed(self):
        # Documented trade-off (docs/DESIGN.md §6): deterministic lexical
        # checking cannot verify translation, so an English answer citing
        # Chinese-only sources blocks instead of passing unexamined.
        result = verify("Reviewers unanimously endorsed immediate rollout.", SRC_ZH)
        self.assertEqual(result["sentence_results"][0]["status"], "blocked")

    def test_fabricated_short_quote_is_blocked(self):
        result = verify(
            'The workflow was "audited" according to the review notes.',
            'The review notes state that the workflow "kept every claim '
            'traceable to its source" during the pilot.',
        )
        row = result["sentence_results"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertIn("audited", row["reason"])

    def test_empty_answer_has_nothing_to_block(self):
        result = verify("", SRC_TIME)
        self.assertTrue(result["publishable"])
        self.assertEqual(result["sentence_results"], [])

    def test_empty_sources_raise(self):
        with self.assertRaises(ValueError):
            verify("Anything.", [])
        with self.assertRaises(ValueError):
            verify("Anything.", {"1": "   "})

    def test_bullets_and_newlines_split_sentences(self):
        answer = "- The error rate fell to 3.5%\n- The error rate fell to 0.2%"
        result = verify(answer, SRC_ERROR)
        statuses = [row["status"] for row in result["sentence_results"]]
        self.assertEqual(statuses, ["verified", "blocked"])

    def test_deep_audit_off_skips_content_checks(self):
        result = verify("The error rate fell to 0.2%.", SRC_ERROR, deep_audit=False)
        self.assertEqual(result["sentence_results"][0]["status"], "verified")
        self.assertFalse(result["deep_audit"])

    def test_verdicts_are_deterministic(self):
        answer = (
            "The error rate fell to 3.5% [1]. Processing time fell to 2.1 minutes. "
            "An audit certified the results [7]."
        )
        sources = {"1": SRC_ERROR, "2": SRC_TIME}
        self.assertEqual(verify(answer, sources), verify(answer, sources))


if __name__ == "__main__":
    unittest.main()
