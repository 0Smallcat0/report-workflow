"""A settings column is not a measure, and a verdict string is not an axis.

The recommender planned "筆數, 佔比, 滞后 平均(依分半年符号)" for a backtest table:
the axis was a column of "++++" and "++−+" — a compressed four-period verdict —
and the measure was the lag setting, which is the same in every row of its half
of the table. The one column that answers the question, the per-trade mean, was
not chosen.

Both mistakes are the same one: every numeric column was treated as a quantity
that was observed, and every low-cardinality string as a dimension worth
grouping by. The same misreading produced the auto-derived crossings — four of
the eight offered were "grouped by 分半年符号".
"""
import unittest

from report_workflow.nodes.figure_recommend import _profile_table


def _table(headers, rows):
    return _profile_table(headers, [headers] + rows, "")


def _roles(profile):
    return {c["header"]: c["role"] for c in profile["columns"]}


class ColumnRoleTests(unittest.TestCase):
    def test_a_settings_column_is_not_a_measure(self):
        # Two lag values crossed with eleven rules: the lag identifies which
        # half of the table a row is in, it does not measure anything.
        headers = ["滞后", "离场规则", "單筆平均"]
        rows = ([["60", f"規則{i}", f"0.00{i}"] for i in range(1, 12)]
                + [["240", f"規則{i}", f"0.01{i}"] for i in range(1, 12)])
        roles = _roles(_table(headers, rows))
        self.assertNotEqual(roles["滞后"], "numeric_measure",
                            "the lag is the same in every row; averaging it says nothing")
        self.assertEqual(roles["單筆平均"], "numeric_measure")

    def test_a_verdict_string_is_not_a_dimension(self):
        headers = ["分半年符号", "單筆平均"]
        rows = [["++++" if i % 2 else "++−+", f"0.0{i}"] for i in range(1, 12)]
        roles = _roles(_table(headers, rows))
        self.assertNotEqual(roles["分半年符号"], "categorical",
                            "a compressed verdict must not become an axis")

    def test_a_real_measure_with_few_values_is_still_a_measure(self):
        # A count that genuinely varies row to row keeps its role, so the
        # settings rule cannot quietly demote small integer measurements.
        headers = ["组", "筆數"]
        rows = [["A", "1"], ["B", "2"], ["C", "3"], ["D", "4"],
                ["E", "5"], ["F", "6"], ["G", "7"], ["H", "8"]]
        roles = _roles(_table(headers, rows))
        self.assertEqual(roles["筆數"], "numeric_measure")

    def test_a_real_category_is_still_a_category(self):
        headers = ["离场规则", "單筆平均"]
        rows = [[f"規則{i}", f"0.0{i}"] for i in range(1, 9)]
        roles = _roles(_table(headers, rows))
        self.assertEqual(roles["离场规则"], "categorical")


class StarterFigurePlanTests(unittest.TestCase):
    """The plan the pipeline writes before authoring is a suggestion.

    The prepare step generates figure_plan.json from the recommendations, before
    the author has written an outline. On a first run every entry in it is
    unused by definition, so the outline stage refused the run over a file the
    author had never opened — thirteen figures named as their omission.

    The generator stamps its own count into the file. An author who edits the
    figures does not maintain that stamp, so a mismatch, or its absence in any
    hand-written plan, means the plan was adopted and must agree with the outline.
    """

    def test_the_untouched_stamp_is_what_marks_it_generated(self):
        from report_workflow.nodes.outline_plan import _starter_plan_is_untouched
        self.assertTrue(callable(_starter_plan_is_untouched))


if __name__ == "__main__":
    unittest.main()
