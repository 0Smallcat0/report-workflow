"""The layout axis measures layout, and not the things it is easy to confuse it with.

Each of these is a way the rule was wrong before it was written down: a numbered
outline scoring as informative because "3.1" contains digits, a document's title
counting as a heading that failed to state a finding, and a table's own rows
counting as the sentence that introduced it.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from report_axes import (  # noqa: E402
    ARGUMENT_DIMENSIONS,
    LAYOUT_DIMENSIONS,
    aggregate_argument_votes,
    heading_informativeness,
    paragraph_length_fitness,
    score_layout,
    table_lead_in_ratio,
    validate_votes,
)

TABLE = "| a | b |\n| --- | --- |\n| 1 | 2 |"


class HeadingInformativenessTests(unittest.TestCase):
    def test_a_heading_that_names_a_topic_says_nothing(self):
        self.assertEqual(heading_informativeness("## 四、買家痛點\n\n內文。"), 0.0)

    def test_a_heading_that_states_a_finding_counts(self):
        self.assertEqual(
            heading_informativeness("## 六、買家痛點：低分不是因為拍得差\n\n內文。"), 1.0
        )

    def test_a_numbered_outline_is_not_informative_by_its_numbering(self):
        # "3.1" is digits that say nothing. Counting them scored a table of
        # contents as a document full of findings.
        self.assertEqual(heading_informativeness("### 3.1 品類結構\n\n內文。"), 0.0)

    def test_a_figure_in_the_heading_counts(self):
        self.assertEqual(
            heading_informativeness("## 三、544 件中只有 267 件可競爭\n\n內文。"), 1.0
        )

    def test_a_colon_with_nothing_after_it_is_not_a_finding(self):
        self.assertEqual(heading_informativeness("## 三、品類結構：概述\n\n內文。"), 0.0)

    def test_the_document_title_is_not_scored(self):
        # A title names the document. Counting it subtracted a fixed unit from
        # every arm, which measured nothing and moved every score.
        text = "# 市場研究報告\n\n## 二、價格帶：需求在低價，錢在中價\n\n內文。"
        self.assertEqual(heading_informativeness(text), 1.0)

    def test_a_document_without_headings_scores_zero_rather_than_dividing_by_zero(self):
        self.assertEqual(heading_informativeness("只有一段文字。"), 0.0)


class TableLeadInTests(unittest.TestCase):
    def test_a_sentence_above_the_table_introduces_it(self):
        text = f"下表列出各價格帶的評論數中位數與銷量覆蓋率。\n\n{TABLE}"
        self.assertEqual(table_lead_in_ratio(text), 1.0)

    def test_a_heading_is_not_a_lead_in(self):
        self.assertEqual(table_lead_in_ratio(f"## 三、價格帶\n\n{TABLE}"), 0.0)

    def test_a_previous_table_is_not_a_lead_in(self):
        text = f"引言句子夠長可以當導讀。\n\n{TABLE}\n\n{TABLE}"
        self.assertEqual(table_lead_in_ratio(text), 0.5)

    def test_a_label_is_too_short_to_be_a_lead_in(self):
        self.assertEqual(table_lead_in_ratio(f"表一\n\n{TABLE}"), 0.0)

    def test_a_document_without_tables_scores_zero(self):
        self.assertEqual(table_lead_in_ratio("沒有表格的一段文字。"), 0.0)


class ParagraphFitnessTests(unittest.TestCase):
    def test_a_one_line_fragment_is_not_a_paragraph(self):
        self.assertEqual(paragraph_length_fitness("下表為來源原始數據。"), 0.0)

    def test_a_paragraph_in_the_readable_band_counts(self):
        self.assertEqual(paragraph_length_fitness("字" * 200), 1.0)

    def test_a_wall_of_text_does_not_count(self):
        self.assertEqual(paragraph_length_fitness("字" * 900), 0.0)

    def test_table_blocks_are_not_paragraphs(self):
        # Otherwise a document scores its own tables as prose and the metric
        # rewards putting everything in a grid.
        self.assertEqual(paragraph_length_fitness(f"{TABLE}\n\n" + "字" * 200), 1.0)


class ScoreLayoutTests(unittest.TestCase):
    def test_every_declared_dimension_is_produced(self):
        scored = score_layout("## 二、價格帶：需求在低價\n\n" + "字" * 200 + f"\n\n{TABLE}")
        self.assertEqual(set(scored), set(LAYOUT_DIMENSIONS))
        for value in scored.values():
            self.assertIsInstance(value, float)

    def test_an_empty_document_scores_zero_on_every_dimension(self):
        self.assertEqual(set(score_layout("").values()), {0.0})


def _vote(number: int, **scores) -> dict:
    vote = {"arm": "hand", "vote": number}
    for dimension in ARGUMENT_DIMENSIONS:
        vote[dimension] = {
            "score": scores.get(dimension, 2),
            "evidence": "第四節指名中位數與絕對值描述兩種結構",
        }
    return vote


class ArgumentVoteTests(unittest.TestCase):
    """The votes are a file, and a file nothing checks can be edited into any result."""

    def test_three_well_formed_votes_aggregate_to_their_median(self):
        votes = [
            _vote(1, claim_strength=4),
            _vote(2, claim_strength=2),
            _vote(3, claim_strength=3),
        ]
        self.assertEqual(aggregate_argument_votes(votes)["claim_strength"], 3)

    def test_one_outlier_does_not_carry_a_dimension(self):
        votes = [
            _vote(1, evidence_depth=0),
            _vote(2, evidence_depth=3),
            _vote(3, evidence_depth=3),
        ]
        self.assertEqual(aggregate_argument_votes(votes)["evidence_depth"], 3)

    def test_two_votes_are_not_enough_for_a_median(self):
        self.assertIn("expected 3 votes", "; ".join(validate_votes([_vote(1), _vote(2)])))

    def test_votes_from_different_arms_are_refused(self):
        votes = [_vote(1), _vote(2), _vote(3)]
        votes[2]["arm"] = "tool"
        self.assertIn("mix arms", "; ".join(validate_votes(votes)))

    def test_a_score_outside_the_rubric_is_refused(self):
        votes = [_vote(1), _vote(2), _vote(3)]
        votes[0]["claim_strength"]["score"] = 7
        self.assertIn("is not an integer 0-4", "; ".join(validate_votes(votes)))

    def test_a_score_with_no_passage_behind_it_is_refused(self):
        votes = [_vote(1), _vote(2), _vote(3)]
        votes[1]["counter_specificity"]["evidence"] = ""
        self.assertIn("cites no passage", "; ".join(validate_votes(votes)))

    def test_aggregating_unusable_votes_raises_rather_than_guessing(self):
        with self.assertRaises(ValueError):
            aggregate_argument_votes([_vote(1)])


if __name__ == "__main__":
    unittest.main()
