"""Contract tests for the HaluEval out-of-domain benchmark.

The 6 MB dataset is not vendored and no test here touches the network. What
is held instead: the scoring logic behaves correctly on a synthetic fixture,
and the archived evidence under ``benchmarks/evidence/halueval_qa_2026-07-15/``
is internally consistent (counts match indices, ratios match counts, the
pinned dataset hash matches the module constant). Full recomputation against
the real dataset is the job of ``run_external_benchmark.py --check``.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_external_benchmark.py"
EVIDENCE_ROOT = ROOT / "benchmarks" / "evidence" / "halueval_qa_2026-07-15"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_external_benchmark", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SYNTHETIC_PAIRS = [
    {
        # Numeric hallucination: FE catches the invented number.
        "knowledge": "The bridge opened in 1932 and spans 503 metres across the bay.",
        "question": "How long is the bridge span?",
        "right_answer": "The bridge spans 503 metres.",
        "hallucinated_answer": "The bridge spans 890 metres.",
    },
    {
        # Entity swap sharing the passage vocabulary: the documented miss class.
        "knowledge": "Arthur's Magazine began publishing before First for Women magazine.",
        "question": "Which magazine was started first?",
        "right_answer": "Arthur's Magazine began publishing first.",
        "hallucinated_answer": "First for Women magazine began publishing first.",
    },
]


class ExternalBenchmarkScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()
        cls.results = cls.module.evaluate_pairs(SYNTHETIC_PAIRS)

    def test_numeric_hallucination_is_caught_and_attributed(self):
        self.assertIn(0, self.results["blocked_hallucinated_indices"])
        self.assertEqual(self.results["gate_breakdown"].get("FE"), 1)

    def test_entity_swap_miss_is_the_documented_boundary(self):
        self.assertNotIn(1, self.results["blocked_hallucinated_indices"])

    def test_right_answers_are_not_blocked(self):
        self.assertEqual(self.results["blocked_right_indices"], [])
        self.assertEqual(self.results["metrics"]["false_positive_rate"], 0.0)

    def test_metric_arithmetic(self):
        metrics = self.results["metrics"]
        self.assertEqual(metrics["true_positives"], 1)
        self.assertEqual(metrics["false_negatives"], 1)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["precision"], 1.0)

    def test_numeric_subset_tracks_only_numeric_pairs(self):
        numeric = self.results["numeric_subset"]
        self.assertEqual(numeric["pairs"], 1)
        self.assertEqual(numeric["caught"], 1)
        self.assertEqual(numeric["recall"], 1.0)


class ExternalBenchmarkArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()
        cls.archived = json.loads(
            (EVIDENCE_ROOT / "results.json").read_text(encoding="utf-8")
        )

    def test_archive_files_exist(self):
        for name in ("results.json", "summary.md"):
            self.assertTrue((EVIDENCE_ROOT / name).exists(), name)

    def test_dataset_pin_matches_module_constant(self):
        self.assertEqual(
            self.archived["dataset"]["sha256"], self.module.DATASET_SHA256
        )
        self.assertEqual(
            self.archived["dataset"]["pairs"], self.module.EXPECTED_PAIRS
        )

    def test_counts_match_indices(self):
        metrics = self.archived["metrics"]
        self.assertEqual(
            metrics["true_positives"],
            len(self.archived["blocked_hallucinated_indices"]),
        )
        self.assertEqual(
            metrics["false_positives"],
            len(self.archived["blocked_right_indices"]),
        )
        self.assertEqual(
            sum(self.archived["gate_breakdown"].values()),
            metrics["true_positives"],
        )

    def test_ratios_match_counts(self):
        metrics = self.archived["metrics"]
        total = self.archived["dataset"]["pairs"]
        self.assertEqual(metrics["recall"], round(metrics["true_positives"] / total, 4))
        self.assertEqual(
            metrics["false_positive_rate"],
            round(metrics["false_positives"] / total, 4),
        )
        self.assertEqual(
            metrics["precision"],
            round(
                metrics["true_positives"]
                / (metrics["true_positives"] + metrics["false_positives"]),
                4,
            ),
        )

    def test_fail_closed_discipline_holds_out_of_domain(self):
        # The adoption claim: out of domain the gate almost never cries wolf.
        metrics = self.archived["metrics"]
        self.assertLessEqual(metrics["false_positive_rate"], 0.001)
        self.assertGreaterEqual(metrics["precision"], 0.99)
        numeric = self.archived["numeric_subset"]
        self.assertGreaterEqual(numeric["recall"], 0.5)


if __name__ == "__main__":
    unittest.main()
