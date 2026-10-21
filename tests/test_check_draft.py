"""check-draft finds each figure and quotation of a finished draft on a page of its sources.

The PDF is drawn here with matplotlib (already a dependency) so the test owns
every word on every page: a two-column first page whose lines are stored
interleaved across the columns, a figure-bearing second page, and a
quotation that runs from the foot of page two onto page three.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from report_workflow.cli import main as cli_main
from report_workflow.draft_check import (
    FOUND,
    NOT_FOUND,
    check_draft,
    checkable_sentences,
    load_source,
    split_sentences,
    states,
    unit_supports,
    units_agree,
)

LEFT = [
    "LLaMA-13B scores 68.9% on the reading",
    "benchmark, well ahead of the baseline.",
    "We find that the smaller model",
    "trains faster than expected on",
    "every corpus we tried.",
] + [f"Left column filler line {i} about apples and orchards." for i in range(36)]
RIGHT = [f"Right column filler line {i} about pears and harbours." for i in range(41)]
PAGE_TWO = [
    "Training took 21 days on 2,048 GPUs for the largest run.",
    "The tokenizer splits all numbers into individual digits.",
    "The authors argue that large models can be trained",
]
PAGE_THREE = [
    "on public data alone, without proprietary datasets.",
    "A closing remark with no figures in it at all.",
]


def _write_pdf(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(str(path)) as pdf:
        figure = plt.figure(figsize=(8.5, 11))
        # Drawn left, right, left, right: stored order runs across the columns.
        for index, (left, right) in enumerate(zip(LEFT, RIGHT)):
            figure.text(0.06, 0.95 - index * 0.022, left, fontsize=8)
            figure.text(0.54, 0.95 - index * 0.022, right, fontsize=8)
        pdf.savefig(figure)
        plt.close(figure)
        for lines, top in ((PAGE_TWO, 0.2), (PAGE_THREE, 0.95)):
            figure = plt.figure(figsize=(8.5, 11))
            for index, line in enumerate(lines):
                figure.text(0.1, top - index * 0.03, line, fontsize=10)
            pdf.savefig(figure)
            plt.close(figure)


CORRECT = """# Notes

LLaMA-13B scores 68.9% on the reading benchmark (Touvron et al., 2023).
Training took 21 days on 2,048 GPUs.
The authors write that "large models can be trained on public data alone".
They also say "We find that the smaller model trains faster than expected".
This sentence states nothing that can be looked up.

## References

Touvron, H. (2023). LLaMA. arXiv:2302.13971.
"""


class _WithSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.pdf = cls.tmp / "paper.pdf"
        _write_pdf(cls.pdf)
        cls.source = load_source(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check(self, text: str):
        results, _ = check_draft([text], [self.source])
        return {item.text: item for result in results for item in result.items}

    def run_cli(self, draft_text: str, *extra: str):
        draft = self.tmp / "draft.md"
        draft.write_text(draft_text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_main(["check-draft", str(draft), "--source", str(self.pdf), *extra])
        return code, out.getvalue(), err.getvalue()


class PrecisionAndUnitsTest(unittest.TestCase):
    def test_a_figure_must_match_at_the_precision_the_draft_gives(self):
        self.assertTrue(states("68.9", "68.9"))
        self.assertTrue(states("69", "68.9"))
        self.assertFalse(states("68.0", "68.9"))
        self.assertFalse(states("68.93", "68.9"))
        self.assertTrue(states("1,022,362", "1022362"))

    def test_a_measured_figure_needs_its_unit_but_a_score_may_be_bare(self):
        self.assertFalse(units_agree("GB", "MB"))
        self.assertTrue(unit_supports("%", ""))
        self.assertFalse(unit_supports("hours", ""))
        self.assertTrue(unit_supports("hours", "h"))
        self.assertTrue(unit_supports("GPUs", ""))


class SentencesTest(unittest.TestCase):
    def test_et_al_and_a_quoted_full_stop_do_not_end_a_sentence(self):
        text = 'Touvron et al. report 63.4. They write "it works. It scales" and stop.'
        self.assertEqual(split_sentences(text), [
            "Touvron et al. report 63.4.",
            'They write "it works. It scales" and stop.',
        ])

    def test_names_citations_and_pointers_are_not_figures(self):
        sentences, others = checkable_sentences([
            "LLaMA-65B with β1 and pass@1 is shown in Table 3 (Touvron et al., 2023). "
            "It reaches 63.4% on MMLU. Nothing to check here."
        ])
        self.assertEqual([s.figures for s in sentences], [[("63.4", "%")]])
        self.assertEqual(others, 2)

    def test_chinese_citation_years_are_not_figures(self):
        sentences, _ = checkable_sentences([
            "Wei 等人（2022）指出準確率 56.9%。王小明（2020）說成長 5%。研究顯示成長 7%（王，2020）。"
            "成長 9%（2020 年資料）。"
        ])
        self.assertEqual([s.figures for s in sentences], [
            [("56.9", "%")], [("5", "%")], [("7", "%")], [("9", "%"), ("2020", "年")],
        ])

    def test_quotations_are_picked_and_short_scare_quotes_are_not(self):
        sentences, _ = checkable_sentences([
            'The "best" model, they write, "is trained only on public data". 作者寫道「這是一段完整的引文」。'
        ])
        self.assertEqual(sentences[0].quotes, ["is trained only on public data"])
        self.assertEqual(sentences[1].quotes, ["這是一段完整的引文"])


class MatchingTest(_WithSource):
    def test_a_correct_figure_is_found_on_its_page(self):
        item = self.check("LLaMA-13B scores 68.9% on the reading benchmark.")["68.9%"]
        self.assertEqual((item.status, item.location.page), (FOUND, 1))

    def test_a_wrong_digit_is_not_found_and_the_page_value_is_named(self):
        item = self.check("LLaMA-13B scores 69.8% on the reading benchmark.")["69.8%"]
        self.assertEqual(item.status, NOT_FOUND)
        self.assertIn("paper.pdf p. 1 states 68.9", item.message)

    def test_extra_decimals_and_a_wrong_unit_are_not_found(self):
        items = self.check("LLaMA-13B scores 68.93% on the reading benchmark. Training took 21 hours on 2,048 GPUs.")
        self.assertEqual(items["68.93%"].status, NOT_FOUND)
        self.assertEqual(items["21 hours"].status, NOT_FOUND)
        self.assertIn("paper.pdf p. 2 states 21 days", items["21 hours"].message)
        self.assertEqual(items["2,048"].status, FOUND)

    def test_a_figure_beside_other_words_is_not_found(self):
        item = self.check("Rainfall in the desert rose 68.9% over the decade.")["68.9%"]
        self.assertEqual(item.status, NOT_FOUND)

    def test_a_quotation_split_across_columns_is_found(self):
        item = self.check('They say "We find that the smaller model trains faster than expected".')[
            "We find that the smaller model trains faster than expected"]
        self.assertEqual((item.status, item.location.page), (FOUND, 1))

    def test_a_quotation_running_onto_the_next_page_is_found(self):
        item = self.check('They write that "large models can be trained on public data alone".')[
            "large models can be trained on public data alone"]
        self.assertEqual(item.status, FOUND)
        self.assertEqual(item.location.label(), "paper.pdf pp. 2–3")

    def test_an_altered_quotation_is_not_found(self):
        item = self.check('They write that "large models can be trained on private data alone".')[
            "large models can be trained on private data alone"]
        self.assertEqual(item.status, NOT_FOUND)


class CommandTest(_WithSource):
    def test_a_correct_draft_exits_0_and_writes_the_appendix_with_pages(self):
        appendix = self.tmp / "appendix.md"
        code, out, _ = self.run_cli(CORRECT, "--appendix", str(appendix), "--json", str(self.tmp / "out.json"))
        self.assertEqual(code, 0, out)
        self.assertIn("4 found, 0 not_found", out)
        text = appendix.read_text(encoding="utf-8")
        self.assertIn("# Source check", text)
        self.assertIn("paper.pdf pp. 2–3", text)
        # The two-column page is quoted in its own sentence order, not across the columns.
        self.assertIn("LLaMA-13B scores 68.9% on the reading benchmark, well ahead of the baseline.", text)
        self.assertNotIn("arXiv:2302.13971", text)
        images = sorted((self.tmp / "appendix_files").glob("*.png"))
        linked = [line for line in text.splitlines() if "appendix_files/" in line]
        # One picture per item found in the PDF, none overwriting another.
        self.assertEqual(len(images), len(linked))
        self.assertEqual(len(images), 5)
        rows = json.loads((self.tmp / "out.json").read_text(encoding="utf-8"))
        self.assertEqual(rows[0]["items"][0]["page"], 1)
        self.assertEqual(rows[0]["items"][0]["source"], "paper.pdf")
        self.assertIn("68.9%", rows[0]["items"][0]["source_sentence"])

    def test_a_draft_with_an_unfound_item_exits_2(self):
        code, out, _ = self.run_cli("LLaMA-13B scores 69.8% on the reading benchmark.\n", "--no-images")
        self.assertEqual(code, 2)
        self.assertIn("69.8% — NOT FOUND", out)

    def test_a_chinese_draft_gets_a_chinese_appendix(self):
        appendix = self.tmp / "zh.md"
        code, _, _ = self.run_cli("在閱讀基準（reading benchmark）的測驗中，LLaMA-13B 模型的得分達到 68.9%，明顯高於基準模型。\n",
                                  "--appendix", str(appendix), "--no-images")
        self.assertEqual(code, 0)
        self.assertIn("# 原件對照", appendix.read_text(encoding="utf-8"))

    def test_a_missing_source_is_an_error_not_a_crash(self):
        draft = self.tmp / "draft.md"
        draft.write_text(CORRECT, encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            code = cli_main(["check-draft", str(draft), "--source", str(self.tmp / "nope.pdf")])
        self.assertEqual(code, 1)
        self.assertIn("No such file", err.getvalue())


if __name__ == "__main__":
    unittest.main()
