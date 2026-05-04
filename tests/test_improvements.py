"""Tests for workflow improvements: sanity gate, table styling, facts freeze, query evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from report_workflow.state import ReportState, register_job_run

# Test pre-render sanity gate
from report_workflow.nodes.docx_render import _pre_render_sanity_check
from report_workflow.nodes.guideline_select import run_guideline_select
from report_workflow.profiles import infer_report_profile, select_reference_template_mode
from report_workflow.prompts.intake_prompt import INTAKE_SYSTEM_PROMPT
from report_workflow.nodes.reference_verify import _is_publication_reference_candidate

# Test agent wrapper entrypoints
from report_workflow.agent_wrapper import query_evidence, start_report_task
from report_workflow.preflight import FeatureDiscovery, FeatureInfo, PreflightResult

# Test profile policy overrides
from report_workflow.policies.policy_pack import get_policy, _POLICY_CACHE


class AgentWrapperPreflightGateTests(unittest.TestCase):
    def _skip_optional_decisions(self):
        return {
            "confirmed_by_user": True,
            "install_decisions": {},
            "feature_decisions": {
                "web_research": "skip",
                "notebook_sync": "skip",
            },
        }

    def _config(self, *, research=False, notebook=False, notebook_id=None):
        return SimpleNamespace(
            enable_research=research,
            enable_notebook_sync=notebook,
            notebooklm_notebook_id=notebook_id,
            notebooklm_storage_path=None,
            as_env_summary=lambda: {
                "enable_research": research,
                "enable_notebook_sync": notebook,
                "notebooklm_notebook_id": notebook_id,
            },
        )

    def _discovery(self, *, research_enabled=False, notebook_enabled=False):
        return FeatureDiscovery(features=[
            FeatureInfo(
                feature_id="web_research",
                name="Web Research",
                description="Ready research backend",
                enabled=research_enabled,
                ready=True,
                missing_setup=[],
                install_commands=[],
                config_flag="enable_research",
            ),
            FeatureInfo(
                feature_id="notebook_sync",
                name="NotebookLM Sync",
                description="Ready notebook integration",
                enabled=notebook_enabled,
                ready=True,
                missing_setup=[],
                install_commands=[],
                config_flag="enable_notebook_sync",
            ),
        ])

    @patch("report_workflow.agent_wrapper.prepare_workflow")
    @patch("report_workflow.agent_wrapper.check_preflight")
    @patch("report_workflow.agent_wrapper.discover_features")
    @patch("report_workflow.agent_wrapper.load_config")
    def test_start_report_task_requires_preflight_confirmation(
        self, mock_config, mock_discovery, mock_preflight, mock_prepare
    ):
        mock_config.return_value = self._config()
        mock_preflight.return_value = PreflightResult(ok=True, missing_packages=[])
        mock_discovery.return_value = self._discovery()

        result = start_report_task("Draft report", [], output_dir="out")

        self.assertEqual(result["status"], "needs_user_decision")
        self.assertTrue(result["agent_should_ask_user"])
        mock_prepare.assert_not_called()

    @patch("report_workflow.agent_wrapper.prepare_workflow")
    @patch("report_workflow.agent_wrapper.check_preflight")
    @patch("report_workflow.agent_wrapper.discover_features")
    @patch("report_workflow.agent_wrapper.load_config")
    def test_start_report_task_allows_explicit_skip_after_confirmation(
        self, mock_config, mock_discovery, mock_preflight, mock_prepare
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("Draft report", [], tmpdir)
            state.status = "completed"
            mock_prepare.return_value = state
            mock_config.return_value = self._config()
            mock_preflight.return_value = PreflightResult(ok=True, missing_packages=[])
            mock_discovery.return_value = self._discovery()

            result = start_report_task(
                "Draft report",
                [],
                output_dir=tmpdir,
                enable_research=False,
                enable_notebook_sync=False,
                preflight_confirmed=True,
                preflight_decisions=self._skip_optional_decisions(),
            )

        self.assertEqual(result["status"], "completed")
        mock_prepare.assert_called_once()

    @patch("report_workflow.agent_wrapper.prepare_workflow")
    @patch("report_workflow.agent_wrapper.check_preflight")
    @patch("report_workflow.agent_wrapper.discover_features")
    @patch("report_workflow.agent_wrapper.load_config")
    def test_start_report_task_blocks_required_dependency_until_preflight_passes(
        self, mock_config, mock_discovery, mock_preflight, mock_prepare
    ):
        mock_config.return_value = self._config()
        mock_preflight.return_value = PreflightResult(ok=False, missing_packages=["pydantic"])
        mock_discovery.return_value = self._discovery()

        result = start_report_task(
            "Draft report",
            [],
            output_dir="out",
            enable_research=False,
            enable_notebook_sync=False,
            preflight_confirmed=True,
            preflight_decisions={
                "confirmed_by_user": True,
                "install_decisions": {
                    "python_packages": "installed",
                },
                "feature_decisions": {
                    "web_research": "skip",
                    "notebook_sync": "skip",
                },
            },
        )

        self.assertEqual(result["status"], "needs_user_decision")
        self.assertIn("Required dependencies", result["message"])
        mock_prepare.assert_not_called()

    @patch("report_workflow.agent_wrapper.prepare_workflow")
    @patch("report_workflow.agent_wrapper.check_preflight")
    @patch("report_workflow.agent_wrapper.discover_features")
    @patch("report_workflow.agent_wrapper.load_config")
    def test_start_report_task_blocks_notebook_without_notebook_id(
        self, mock_config, mock_discovery, mock_preflight, mock_prepare
    ):
        mock_config.return_value = self._config(notebook=True, notebook_id=None)
        mock_preflight.return_value = PreflightResult(ok=True, missing_packages=[])
        mock_discovery.return_value = self._discovery(notebook_enabled=True)

        result = start_report_task(
            "Draft report",
            [],
            output_dir="out",
            enable_notebook_sync=True,
            preflight_confirmed=True,
            preflight_decisions={
                "confirmed_by_user": True,
                "install_decisions": {},
                "feature_decisions": {
                    "web_research": "skip",
                    "notebook_sync": "enable",
                },
            },
        )

        self.assertEqual(result["status"], "needs_user_decision")
        self.assertIn("notebooklm_notebook_id", result["message"])
        mock_prepare.assert_not_called()

    @patch("report_workflow.agent_wrapper.prepare_workflow")
    @patch("report_workflow.agent_wrapper.check_preflight")
    @patch("report_workflow.agent_wrapper.discover_features")
    @patch("report_workflow.agent_wrapper.load_config")
    def test_start_report_task_blocks_missing_critical_render_dependency(
        self, mock_config, mock_discovery, mock_preflight, mock_prepare
    ):
        mock_config.return_value = self._config()
        mock_preflight.return_value = PreflightResult(
            ok=True,
            missing_packages=[],
            external_tool_warnings=[{
                "tool": "pandoc",
                "severity": "critical",
                "installed": False,
                "install_command": "winget install JohnMacFarlane.Pandoc",
                "description": "Required for high-quality DOCX rendering.",
            }],
        )
        mock_discovery.return_value = self._discovery()

        result = start_report_task(
            "Draft report",
            [],
            output_dir="out",
            enable_research=False,
            enable_notebook_sync=False,
            preflight_confirmed=True,
            preflight_decisions={
                "confirmed_by_user": True,
                "install_decisions": {
                    "pandoc": "install",
                },
                "feature_decisions": {
                    "web_research": "skip",
                    "notebook_sync": "skip",
                },
            },
        )

        self.assertEqual(result["status"], "needs_user_decision")
        self.assertIn("Critical render dependencies", result["message"])
        mock_prepare.assert_not_called()

    @patch("report_workflow.agent_wrapper.prepare_workflow")
    @patch("report_workflow.agent_wrapper.check_preflight")
    @patch("report_workflow.agent_wrapper.discover_features")
    @patch("report_workflow.agent_wrapper.load_config")
    def test_start_report_task_requires_accept_degraded_for_degraded_render(
        self, mock_config, mock_discovery, mock_preflight, mock_prepare
    ):
        mock_config.return_value = self._config()
        mock_preflight.return_value = PreflightResult(
            ok=True,
            missing_packages=[],
            external_tool_warnings=[{
                "tool": "pandoc",
                "severity": "critical",
                "installed": False,
                "install_command": "winget install JohnMacFarlane.Pandoc",
                "description": "Required for high-quality DOCX rendering.",
            }],
        )
        mock_discovery.return_value = self._discovery()

        result = start_report_task(
            "Draft report",
            [],
            output_dir="out",
            enable_research=False,
            enable_notebook_sync=False,
            preflight_confirmed=True,
            allow_degraded_render=True,
            preflight_decisions={
                "confirmed_by_user": True,
                "install_decisions": {
                    "pandoc": "install",
                },
                "feature_decisions": {
                    "web_research": "skip",
                    "notebook_sync": "skip",
                },
            },
        )

        self.assertEqual(result["status"], "needs_user_decision")
        self.assertIn("accept", result["message"])
        mock_prepare.assert_not_called()

    @patch("report_workflow.agent_wrapper.prepare_workflow")
    @patch("report_workflow.agent_wrapper.check_preflight")
    @patch("report_workflow.agent_wrapper.discover_features")
    @patch("report_workflow.agent_wrapper.load_config")
    def test_start_report_task_rejects_boolean_confirmation_without_decision_record(
        self, mock_config, mock_discovery, mock_preflight, mock_prepare
    ):
        mock_config.return_value = self._config()
        mock_preflight.return_value = PreflightResult(ok=True, missing_packages=[])
        mock_discovery.return_value = self._discovery()

        result = start_report_task(
            "Draft report",
            [],
            output_dir="out",
            enable_research=False,
            enable_notebook_sync=False,
            preflight_confirmed=True,
        )

        self.assertEqual(result["status"], "needs_user_decision")
        self.assertIn("preflight_decisions", result["decision_issues"][0])
        mock_prepare.assert_not_called()


class PreRenderSanityGateTests(unittest.TestCase):
    """Test _pre_render_sanity_check function."""

    def test_clean_document_passes(self):
        md = "# Title\n\n## Abstract\n\nSome text here.\n\n## Introduction\n\nMore text.\n"
        issues = _pre_render_sanity_check(md)
        self.assertEqual(issues, [])

    def test_duplicated_heading_detected(self):
        md = "# Title\n\n## Abstract\n\nText.\n\n## Abstract\n\nDuplicate.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Duplicated heading" in i for i in issues))

    def test_duplicated_references_detected(self):
        md = "## References\n\nRef1.\n\n## References\n\nRef2.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Multiple References" in i for i in issues))

    def test_placeholder_metadata_detected(self):
        md = "Author: [Author Name]\nUniversity: [University]\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Placeholder metadata" in i for i in issues))

    def test_unresolved_cite_detected(self):
        md = "This claim [CITE:E001] is unresolved.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("[CITE:]" in i for i in issues))

    def test_prompt_and_metadata_leakage_detected(self):
        md = (
            "# {.Title} Revise the base document as an academic report\n\n"
            "Author\n\nIndependent Researcher\n\n"
            "Correspondence: author@example.com\n\n"
            "Keywords: Corpus, Backtrader, Pydantic, Kelly, Bayesian, Ollama\n"
        )
        issues = _pre_render_sanity_check(md)
        joined = "; ".join(issues)
        self.assertIn("Pandoc title marker", joined)
        self.assertIn("raw task instruction", joined)
        self.assertIn("generic template", joined)
        self.assertIn("implementation-noise", joined)

    def test_prompt_fragment_detected(self):
        prompt = "Write an admissions-facing academic project report on deterministic compilation architecture."
        md = f"# Title\n\n{prompt}\n"
        issues = _pre_render_sanity_check(md, forbidden_fragments=[prompt])
        self.assertTrue(any("Raw prompt fragment" in i for i in issues))

    def test_internal_pseudo_citation_detected(self):
        md = "The system is deterministic (source & corpus (n.d.)).\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("pseudo-citation" in i for i in issues))

    def test_internal_source_corpus_detected(self):
        md = "## References\n\n- source & corpus. (2026). *source_corpus* [Text file].\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("source_corpus" in i for i in issues))

    def test_internal_markers_detected(self):
        md = "Some text [Source: internal file] here.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Internal markers" in i for i in issues))

    def test_end_of_report_sentinel_detected(self):
        md = "## End of Main Report\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("sentinel" in i.lower() for i in issues))

    def test_facts_freeze_pass(self):
        md = "We analyzed 388 files with 5,171 nodes.\n"
        freeze = {"total_files": "388", "graph_nodes": "5,171"}
        issues = _pre_render_sanity_check(md, freeze)
        self.assertEqual(issues, [])

    def test_facts_freeze_violation(self):
        md = "We analyzed 386 files.\n"
        freeze = {"total_files": "388"}
        issues = _pre_render_sanity_check(md, freeze)
        self.assertTrue(any("Facts freeze violation" in i for i in issues))

    def test_ascii_art_detected(self):
        md = "```\n????????n??Box  ?n????????n```\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("ASCII art" in i for i in issues))

    def test_traceability_appendix_detected(self):
        md = "See traceability_appendix for details.\n"
        issues = _pre_render_sanity_check(md)
        self.assertTrue(any("Traceability appendix" in i for i in issues))


class QueryEvidenceTests(unittest.TestCase):
    """Test query_evidence agent tool."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.job_id = "test_query_job"
        self.run_dir = Path(self.tmpdir) / f"query-evidence--{self.job_id}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        register_job_run(self.job_id, self.run_dir)

        # Write test evidence ledger
        entries = []
        for i in range(1, 26):
            entries.append(json.dumps({
                "evidence_id": f"E{i:03d}",
                "source_file_name": f"file_{i}.py",
                "evidence_type": "code_artifact",
                "quote": f"Evidence text for entry {i}",
            }))
        (self.run_dir / "evidence_ledger.jsonl").write_text(
            "\n".join(entries), encoding="utf-8"
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_query_by_ids(self):
        result = query_evidence(self.job_id, evidence_ids=["E001", "E005"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["returned"], 2)
        self.assertEqual(result["total_entries"], 25)
        ids = {e["evidence_id"] for e in result["entries"]}
        self.assertEqual(ids, {"E001", "E005"})

    def test_query_missing_ids(self):
        result = query_evidence(self.job_id, evidence_ids=["E001", "E999"])
        self.assertEqual(result["returned"], 1)
        self.assertIn("E999", result["missing_ids"])

    def test_paginated_browsing(self):
        result = query_evidence(self.job_id, offset=0, limit=10)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["returned"], 10)
        self.assertTrue(result["has_more"])

    def test_paginated_last_page(self):
        result = query_evidence(self.job_id, offset=20, limit=10)
        self.assertEqual(result["returned"], 5)
        self.assertFalse(result["has_more"])

    def test_limit_capped_at_50(self):
        result = query_evidence(self.job_id, offset=0, limit=100)
        # Should be capped internally but return all 25 since total < 50
        self.assertEqual(result["returned"], 25)

    def test_missing_ledger(self):
        result = query_evidence("nonexistent_job_id")
        self.assertEqual(result["status"], "error")


class PolicyProfileTests(unittest.TestCase):
    """Test profile policy overrides."""

    def setUp(self):
        _POLICY_CACHE.clear()

    def test_default_academic_requires_structure(self):
        policy = get_policy("academic_paper")
        self.assertTrue(policy.abstract.structure_required)
        self.assertEqual(policy.abstract.word_count_min, 180)

    def test_admissions_profile_relaxes_abstract(self):
        policy = get_policy("admissions_report")
        self.assertFalse(policy.abstract.structure_required)
        self.assertTrue(policy.abstract.allow_plain_paragraph)
        self.assertEqual(policy.abstract.word_count_min, 150)
        self.assertEqual(policy.abstract.word_count_max, 250)

    def test_admissions_profile_preserves_other_policies(self):
        policy = get_policy("admissions_report")
        # Other policies should remain unchanged
        self.assertTrue(policy.front_matter.required)
        self.assertTrue(policy.claim.thesis_required)
        self.assertEqual(policy.citation.style, "APA")

    def test_intake_infers_admissions_profile(self):
        profile = infer_report_profile(
            "Write an admissions-facing academic project report for graduate school admissions."
        )
        self.assertEqual(profile, "admissions_project_report")

    def test_custom_profile_defaults_are_lenient(self):
        policy = get_policy("custom")
        self.assertEqual(policy.abstract.word_count_min, 0)
        self.assertFalse(policy.reference.doi_verification_required)
        self.assertFalse(policy.reference.reality_report_required)
        self.assertFalse(policy.citation.source_marker_hard_block)
        self.assertTrue(policy.claim.role_validation_required)

    def test_custom_profile_has_no_default_clinical_guideline(self):
        state = ReportState.new("plain custom report", [], "out")
        state.spec["report_profile"] = "custom"
        state.spec["keywords"] = []
        state = run_guideline_select(state)
        self.assertEqual(state.spec["selected_guidelines"], [])

    def test_reference_template_fixed_markers_are_case_insensitive(self):
        self.assertEqual(
            select_reference_template_mode("academic_paper", "Use the Exact Format from the base document."),
            "fixed_template",
        )
        self.assertEqual(
            select_reference_template_mode("academic_paper", "\u5b8c\u5168\u7167\u683c\u5f0f"),
            "fixed_template",
        )

    def test_intake_prompt_lists_current_profiles(self):
        for profile in (
            "engineering_lab_report",
            "academic_paper",
            "business_report",
            "proposal",
            "admissions_report",
            "admissions_project_report",
            "custom",
        ):
            self.assertIn(profile, INTAKE_SYSTEM_PROMPT)
        self.assertIn("report_profile_description", INTAKE_SYSTEM_PROMPT)
        self.assertNotIn('"report_profile": "string description"', INTAKE_SYSTEM_PROMPT)


class ReferenceCurationTests(unittest.TestCase):
    def test_internal_text_reference_is_not_publication_candidate(self):
        self.assertFalse(
            _is_publication_reference_candidate("source & corpus. (2026). source_corpus [Text file].")
        )

    def test_book_reference_is_publication_candidate(self):
        self.assertTrue(
            _is_publication_reference_candidate("Lopez-de Prado, M. (2018). *Advances in financial machine learning*. John Wiley & Sons.")
        )

    def tearDown(self):
        _POLICY_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
