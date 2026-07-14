"""Contract tests for the adversarial anti-hallucination benchmark.

The corpus in ``scripts/run_adversarial_benchmark.py`` doubles as a regression
suite for the factuality gate stack: every case records the verdict the gates
are expected to produce, and the archived evidence under
``benchmarks/evidence/adversarial_2026-07-14/`` must be reproducible from
source. These tests re-run the benchmark in-process (it is fast, offline, and
deterministic) and hold both properties.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_adversarial_benchmark.py"
EVIDENCE_ROOT = ROOT / "benchmarks" / "evidence" / "adversarial_2026-07-14"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_adversarial_benchmark", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AdversarialBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_module()
        cls.results = cls.module.build_results()

    def test_corpus_is_well_formed(self):
        cases = self.module.CASES
        case_ids = [case["case_id"] for case in cases]

        self.assertEqual(len(case_ids), len(set(case_ids)), "case_ids must be unique")
        self.assertGreaterEqual(len(cases), 50)
        honest = [case for case in cases if not case["is_hallucination"]]
        hallucinated = [case for case in cases if case["is_hallucination"]]
        self.assertGreaterEqual(len(honest), 15)
        self.assertGreaterEqual(len(hallucinated), 30)

        for case in cases:
            self.assertIn(case["expected_verdict"], {"published", "blocked"})
            self.assertTrue(case["note"], f"{case['case_id']} must document why it exists")
            # Honest controls must never be expected to block.
            if not case["is_hallucination"]:
                self.assertEqual(case["expected_verdict"], "published", case["case_id"])

    def test_unknown_evidence_ids_only_appear_in_citation_attacks(self):
        for case in self.module.CASES:
            unknown = [
                eid for eid in case["claim"]["evidence_ids"]
                if eid not in self.module.LEDGER_IDS
            ]
            if unknown:
                self.assertEqual(
                    case["family"], "fabricated_citation",
                    f"{case['case_id']} cites unknown evidence outside the citation-attack family",
                )

    def test_gate_stack_matches_expected_verdicts(self):
        self.assertEqual(self.results["expected_mismatches"], [])

    def test_no_false_positives_on_honest_claims(self):
        metrics = self.results["checkers"]["full_gate_stack"]["metrics"]
        self.assertEqual(metrics["false_positives"], 0)
        self.assertEqual(metrics["false_positive_rate"], 0.0)

    def test_recall_beats_both_baselines(self):
        recalls = {
            config: self.results["checkers"][config]["metrics"]["recall"]
            for config in self.module.CHECKER_CONFIGS
        }
        self.assertEqual(recalls["no_gate"], 0.0)
        self.assertLess(recalls["citation_presence"], recalls["full_gate_stack"])
        # Ratchet: 0.75 before the 2026-07-14 gate hardening, 0.85 after it.
        # Raise this floor whenever a gate improvement lifts measured recall.
        self.assertGreaterEqual(recalls["full_gate_stack"], 0.85)

    def test_targeted_families_are_fully_caught(self):
        for entry in self.results["checkers"]["full_gate_stack"]["family_breakdown"]:
            if entry["family"].startswith("evasion_"):
                self.assertEqual(entry["caught"], 0, entry["family"])
            else:
                self.assertEqual(entry["caught"], entry["cases"], entry["family"])

    def test_documented_evasions_stay_documented(self):
        evasions = [
            case for case in self.module.CASES
            if case["is_hallucination"] and case["expected_verdict"] == "published"
        ]
        self.assertEqual(len(evasions), self.results["corpus"]["documented_evasions"])
        for case in evasions:
            self.assertTrue(case["family"].startswith("evasion_"), case["case_id"])

    def test_repeated_runs_are_deterministic(self):
        self.assertTrue(self.results["determinism"]["identical"])
        rerun = self.module.build_results()
        self.assertEqual(
            rerun["determinism"]["verdict_hash"],
            self.results["determinism"]["verdict_hash"],
        )

    def test_archived_evidence_is_reproducible_from_source(self):
        issues = self.module.check_archive()
        self.assertEqual(issues, [], "archived adversarial evidence drifted from source")

    def test_archived_summary_files_exist(self):
        for name in ("corpus.json", "results.json", "summary.md"):
            self.assertTrue((EVIDENCE_ROOT / name).exists(), name)
        archived = json.loads((EVIDENCE_ROOT / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(
            archived["corpus"]["corpus_hash"],
            self.results["corpus"]["corpus_hash"],
        )


if __name__ == "__main__":
    unittest.main()
