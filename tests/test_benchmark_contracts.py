import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "benchmarks"

EXPECTED_PROFILES = {
    "engineering_lab_report",
    "academic_paper",
    "business_report",
    "proposal",
    "admissions_report",
    "admissions_project_report",
    "custom",
}

GAP_CATEGORIES = {
    "skill_guidance_gap",
    "profile_policy_gap",
    "deterministic_pipeline_gap",
    "render_template_gap",
    "agent_authoring_gap",
    "external_reference_gap",
}

EXPECTED_CHART_FIXTURES = {
    "fixtures/chart_source.csv",
    "fixtures/chart_line_source.csv",
    "fixtures/chart_scatter_source.csv",
    "fixtures/chart_boxplot_source.csv",
    "fixtures/chart_table_fallback_source.csv",
}

EXPECTED_FIGURE_TYPES = {"bar", "line", "scatter", "boxplot", "table"}


class BenchmarkContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings = json.loads((BENCHMARK_ROOT / "findings.json").read_text(encoding="utf-8"))
        cls.matrix = (BENCHMARK_ROOT / "report_quality_matrix.md").read_text(encoding="utf-8")

    def test_findings_cover_all_builtin_profiles(self):
        profiles = {entry["report_profile"] for entry in self.findings["profiles"]}

        self.assertEqual(profiles, EXPECTED_PROFILES)
        self.assertEqual(self.findings["public_interface_selector"], "report_profile")
        self.assertNotIn("report_profile_variant", self.findings)

    def test_gap_taxonomy_is_fixed_and_used_by_findings(self):
        self.assertEqual(set(self.findings["gap_categories"]), GAP_CATEGORIES)

        for profile in self.findings["profiles"]:
            for gap in profile["initial_gaps"]:
                self.assertIn(gap["category"], GAP_CATEGORIES)
        for action in self.findings["ranked_actions"]:
            self.assertIn(action["category"], GAP_CATEGORIES)

    def test_each_profile_has_packet_fixture_sources_and_qa_artifacts(self):
        for profile in self.findings["profiles"]:
            case_path = BENCHMARK_ROOT / profile["benchmark_case"]
            fixture_path = BENCHMARK_ROOT / profile["fixture"]
            chart_fixtures = set(profile["chart_fixtures"])

            self.assertTrue(case_path.exists(), profile["report_profile"])
            self.assertTrue(fixture_path.exists(), profile["report_profile"])
            self.assertEqual(chart_fixtures, EXPECTED_CHART_FIXTURES)
            for chart_fixture in chart_fixtures:
                self.assertTrue((BENCHMARK_ROOT / chart_fixture).exists(), profile["report_profile"])
            self.assertGreaterEqual(len(profile["rubric_sources"]), 1)
            self.assertGreaterEqual(len(profile["qa_artifacts"]), 1)
            case_text = case_path.read_text(encoding="utf-8")
            self.assertIn("## Expected Output", case_text)
            self.assertIn("## Gap Categories To Check", case_text)

    def test_matrix_and_skill_docs_explain_benchmark_first_workflow(self):
        self.assertIn("report_profile", self.matrix)
        for profile in EXPECTED_PROFILES:
            self.assertIn(profile, self.matrix)
        for category in GAP_CATEGORIES:
            self.assertIn(category, self.matrix)

        skill = (ROOT / "skills/report-workflow" / "SKILL.md").read_text(encoding="utf-8")
        benchmarking = (
            ROOT / "skills/report-workflow" / "reference" / "benchmarking.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Benchmark-First Optimization", skill)
        self.assertIn("Benchmark-First Optimization", benchmarking)
        self.assertIn("benchmarks/findings.json", benchmarking)
        self.assertIn("scripts/run_report_benchmarks.py --check", skill)
        self.assertIn("scripts/run_report_benchmarks.py --check", benchmarking)

    def test_prepare_smoke_is_recorded_without_claiming_full_publish(self):
        smoke = self.findings["prepare_smoke"]

        self.assertEqual(smoke["status"], "pass")
        self.assertEqual(smoke["expected_workflow_status"], "awaiting_agent_artifacts")
        self.assertIn("prepare workflow only", smoke["scope"])
        smoke_path = BENCHMARK_ROOT / smoke["evidence_path"]
        self.assertTrue(smoke_path.exists())
        smoke_text = smoke_path.read_text(encoding="utf-8")
        for profile in EXPECTED_PROFILES:
            self.assertIn(profile, smoke_text)

    def test_full_benchmark_evidence_is_recorded(self):
        full = self.findings["full_benchmark"]

        self.assertEqual(full["status"], "pass")
        self.assertEqual(full["profiles_total"], len(EXPECTED_PROFILES))
        self.assertEqual(full["profiles_passed"], len(EXPECTED_PROFILES))
        self.assertEqual(full["profiles_failed"], 0)
        self.assertEqual(full["check_command"], "python scripts/run_report_benchmarks.py --check")
        self.assertEqual(full["chart_coverage"]["status"], "pass")
        self.assertEqual(set(full["chart_coverage"]["expected_recommendation_types"]), EXPECTED_FIGURE_TYPES)
        self.assertEqual(
            full["chart_coverage"]["profiles_with_figure_recommendations"],
            len(EXPECTED_PROFILES),
        )
        self.assertEqual(set(full["chart_coverage"]["profiles_with_full_type_coverage"]), EXPECTED_PROFILES)
        self.assertTrue(EXPECTED_CHART_FIXTURES.issubset(set(full["fixtures"])))
        self.assertTrue((ROOT / full["runner"]).exists())

        summary_path = BENCHMARK_ROOT / full["summary_path"]
        self.assertTrue(summary_path.exists())
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["counts"]["total"], len(EXPECTED_PROFILES))
        self.assertEqual(summary["counts"]["pass"], len(EXPECTED_PROFILES))
        self.assertEqual(summary["counts"]["failed"], 0)
        summary_fixtures = {fixture.replace("\\", "/") for fixture in summary["fixtures"]}
        self.assertTrue(
            {f"benchmarks/{fixture}" for fixture in EXPECTED_CHART_FIXTURES}.issubset(summary_fixtures)
        )

        for profile in summary["profiles"]:
            digest = profile["qa_digest"]
            roles = {snapshot["role"] for snapshot in profile["snapshots"]}

            self.assertEqual(digest["figure_recommendations"]["status"], "available")
            self.assertEqual(digest["figure_visual_quality"]["status"], "passed")
            self.assertGreaterEqual(
                digest["figure_recommendations"]["recommendation_count"],
                len(EXPECTED_FIGURE_TYPES),
            )
            self.assertTrue(
                EXPECTED_FIGURE_TYPES.issubset(set(digest["figure_recommendations"]["recommended_types"]))
            )
            self.assertIn(digest["figure_plan_audit"]["status"], {"passed", "passed_with_warnings"})
            self.assertGreaterEqual(digest["figure_plan_audit"]["figure_count"], len(EXPECTED_FIGURE_TYPES))
            self.assertTrue(
                EXPECTED_FIGURE_TYPES.issubset(set(digest["figure_plan_audit"]["planned_types"]))
            )
            self.assertIn("figure_plan_audit_report.json", roles)
            self.assertIn("figure_visual_quality_report.json", roles)
            self.assertIn("published/final_qa_summary.json", roles)


if __name__ == "__main__":
    unittest.main()
