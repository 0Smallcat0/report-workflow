"""The register gate catches what shipped, and leaves what should ship alone.

Every string in FROM_A_DELIVERED_DOCUMENT reached a delivered .docx through the
whole pipeline — claim verification, factuality, lint, publish — because the only
tone check in the tool returns immediately unless the profile is
`admissions_report`.

MUST_SURVIVE is the other half, and matters more: a gate that also refuses good
prose gets switched off. A quoted requirement is the question the report answers;
a results table naming a measured value is the report doing its job.
"""
import unittest

from report_workflow.nodes.register_gate import find_register_issues


FROM_A_DELIVERED_DOCUMENT: tuple[tuple[str, str], ...] = (
    ("導師 2026-08-28：「辛苦你研究如何提高回購事件的收益率」。", "chat attribution"),
    ("指派內容原話：完成 2 個回測。", "chat attribution"),
    ("也就是說這 105 筆裡還有東西，而我兩次都沒把它命名出來。", "first-person process narration"),
    ("還有一件要自己認的事：分類做了兩版，第一版把 244 筆丟進其他。", "development-process confession"),
    ("這條是因為第一版差點用錯欄位。", "development-process confession"),
    ("| 離場條件 | ❌ 二十個格子全部比固定持有差 |", "emoji"),
    ("要一句話：能提高的是買什麼。", "blog connective"),
    ("At first I mislabelled the column, then corrected it.", "development-process confession"),
)

MUST_SURVIVE: tuple[str, ...] = (
    "> 回购、增持相关事件辛苦用东财的 7×24 小时数据做一个回测，离场条件自己定。",
    "| 固定持有（基準） | +0.98% | — | +1.16% | — |",
    "離場條件在任務規則裡未指定，是唯一可自訂的環節。",
    "每一桶有自己的無條件對照，事件均值減掉同批股票隨機時點的均值才是事件效應。",
    "滯後 60 分鐘、持有 5 交易日時，固定持有的單筆平均淨收益為 0.98 個百分點。",
    "The residual bucket holds information this round did not isolate.",
    "```\nprint('我')\n```",
)


class RegisterGateTests(unittest.TestCase):
    def test_every_shipped_violation_is_caught(self):
        for text, label in FROM_A_DELIVERED_DOCUMENT:
            with self.subTest(text=text):
                issues = find_register_issues(text)
                self.assertTrue(issues, f"not caught: {text}")
                self.assertTrue(
                    any(label in issue for issue in issues),
                    f"caught as the wrong kind: {issues}",
                )

    def test_report_prose_is_left_alone(self):
        for text in MUST_SURVIVE:
            with self.subTest(text=text):
                self.assertEqual(
                    find_register_issues(text), [],
                    "a gate that refuses good prose gets switched off",
                )

    def test_the_issue_names_the_line_and_the_remedy(self):
        issue = find_register_issues("要一句話：能提高的是買什麼。")[0]
        self.assertIn("line 1", issue)
        self.assertIn("blog connective", issue)
        self.assertIn("state the point", issue)


if __name__ == "__main__":
    unittest.main()
