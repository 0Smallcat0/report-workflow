"""The report-quality benchmark has to keep being reproducible and honest.

Its whole value is that someone else can run it and get the same numbers. A
benchmark whose archive drifts from its source is a claim with no evidence
behind it, so the archive is asserted here the way the adversarial one is.
"""
import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_report_quality_benchmark.py"
EVIDENCE_ROOT = REPO_ROOT / "benchmarks" / "evidence" / "report_quality_2026-08-06"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_report_quality_benchmark", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScorerTests(unittest.TestCase):
    """One scorer reads both arms, so it has to be arm-agnostic."""

    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()

    def test_apparatus_is_not_read_as_prose(self):
        """A generated source entry is not a paragraph the author wrote.

        Its line numbers and evidence-id digits would otherwise count as
        unverifiable figures, and its single line as an unstructured
        paragraph — scoring the pipeline's own apparatus against the pipeline.
        """
        text = (
            "這是一段正文。它有第二句。還有第三句。\n\n"
            "[S1] recycling.md line 5-8 — E_abc123def4 — “引文”\n\n"
            "來源：recycling.md line 10-15\n\n"
            "表 2. 回收成本\n"
        )
        self.assertEqual(len(self.module._body_paragraphs(text)), 1)

    def test_a_chinese_numeral_is_not_a_checkable_figure(self):
        source = "價格為 80,000 美元。"
        vague = "價格大約八萬美元。"
        exact = "價格為 80,000 美元，此為來源所載。"
        self.assertEqual(self.module.verifiable_numbers(vague, source), 0)
        self.assertEqual(self.module.verifiable_numbers(exact, source), 1)

    def test_the_ratio_alone_rewards_saying_nothing(self):
        """Documented so nobody reads the ratio without the count."""
        source = "回收率 95%，成本 210 美元，價差 77 美元。"
        says_one_thing = "回收率為 95%。"
        self.assertEqual(self.module.verifiable_number_ratio(says_one_thing, source), 1.0)
        self.assertEqual(self.module.verifiable_numbers(says_one_thing, source), 1)

    def test_a_derivation_counts_only_when_it_shows_its_working(self):
        bare = "【推算】單噸收入約為 2,383 美元。"
        shown = "【推算】單噸收入約為 2,383 美元（21,665 × 0.11）。"
        self.assertEqual(self.module.count_disclosed_derivations(bare), 0)
        self.assertEqual(self.module.count_disclosed_derivations(shown), 1)

    def test_external_sources_are_counted_across_the_whole_document(self):
        """Including the apparatus: a source in the list is still a source."""
        text = "見下表（來源：Fastmarkets，2026）。\n\n[S1] a.md — https://example.org/x\n"
        self.assertEqual(self.module.count_external_sources(text), 2)


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()

    def test_the_recorded_baseline_is_not_a_strawman(self):
        """A rigged baseline would make every other number here meaningless."""
        baseline = self.module.BASELINE_PATH.read_text(encoding="utf-8")
        source = self.module.SOURCE_PATH.read_text(encoding="utf-8")
        scores = self.module.score_document(baseline, source)
        self.assertGreaterEqual(
            scores["structured_paragraph_ratio"], 0.6,
            "the baseline's prose structure is too weak to be a fair comparison",
        )
        self.assertGreaterEqual(
            scores["counter_evidence_paragraphs"], 1,
            "the baseline presents no counter-evidence at all, which is not credible",
        )

    def test_the_source_carries_what_the_benchmark_measures(self):
        source = self.module.SOURCE_PATH.read_text(encoding="utf-8")
        self.assertGreaterEqual(self.module.count_tables(source), 4)
        self.assertGreaterEqual(self.module.count_external_sources(source), 8)
        self.assertGreaterEqual(self.module.count_disclosed_derivations(source), 3)


class ArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()
        cls.archived = json.loads(
            (EVIDENCE_ROOT / "results.json").read_text(encoding="utf-8")
        )

    def test_archived_files_exist(self):
        for name in ("results.json", "summary.md"):
            self.assertTrue((EVIDENCE_ROOT / name).exists(), name)

    def test_the_archive_reproduces_from_source(self):
        issues = self.module.check_archive()
        self.assertEqual(issues, [], "archived report-quality evidence drifted from source")

    def test_the_tool_arm_wins_most_dimensions(self):
        self.assertGreater(
            self.archived["tool_wins"],
            self.archived["unassisted_wins"],
            "the harness no longer improves the deliverable on most dimensions",
        )

    def test_the_dimensions_that_motivated_the_work_are_won(self):
        """The three the tester measured as zero in the delivered document."""
        by_dimension = {row["dimension"]: row for row in self.archived["comparison"]}
        for dimension in ("external_sources", "tables", "verifiable_numbers"):
            with self.subTest(dimension=dimension):
                self.assertEqual(by_dimension[dimension]["winner"], "tool")
                self.assertGreater(by_dimension[dimension]["tool"], 0)

    def test_losses_are_still_recorded(self):
        """If a loss silently disappears, check whether it was fixed or hidden."""
        losers = [
            row["dimension"]
            for row in self.archived["comparison"]
            if row["winner"] == "unassisted"
        ]
        self.assertEqual(
            sorted(losers),
            ["structured_paragraph_ratio", "verifiable_number_ratio"],
            "the recorded losses changed; update the summary's explanation of them",
        )


if __name__ == "__main__":
    unittest.main()
