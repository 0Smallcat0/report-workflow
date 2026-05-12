import io
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docx import Document

from report_workflow.cli import main as cli_main
from report_workflow.errors import AgentWorkRequired, QAHardBlockError
from report_workflow.nodes.artifacts import run_artifacts
from report_workflow.nodes.corpus_build import run_corpus_build
from report_workflow.nodes.evidence_normalize import run_evidence_normalize
from report_workflow.nodes.evidence_store import run_evidence_store
from report_workflow.nodes.factuality_check import run_factuality_check, run_factuality_check_fa, run_factuality_check_fb, run_factuality_check_fd, run_factuality_check_fe
from report_workflow.nodes.consistency_check import run_consistency_check
from report_workflow.nodes.guideline_check import run_guideline_check, _check_guideline, _split_by_sections
from report_workflow.nodes.figure_quality import run_figure_quality, _check_figure_contract, _check_no_audit_tables_in_main_text
from report_workflow.nodes.citation_bind import resolve_citations
from report_workflow.nodes.figure_build import run_figure_build
from report_workflow.nodes.guideline_select import run_guideline_select
from report_workflow.nodes.intake import run_intake
from report_workflow.nodes.merge_draft import _canonicalize_section_content
from report_workflow.nodes.methods_protocol_build import run_methods_protocol_build
from report_workflow.nodes.qa_gate import run_qa_gate
from report_workflow.nodes.section_plan_freeze import run_section_plan_freeze
from report_workflow.nodes.source_parse import run_source_parse
from report_workflow.preflight import (
    FeatureDiscovery,
    FeatureInfo,
    PreflightResult,
    check_preflight,
    run_preflight_checks,
)
from report_workflow.run_workflow import prepare_workflow, render_workflow, resume_workflow, run_workflow, status_workflow, validate_workflow
from report_workflow.config import PROJECT_ROOT
from report_workflow.state import (
    ReportState,
    WORKFLOW_RUNS_DIR,
    clear_job_run_hints,
    default_workspace_root,
    register_job_run,
)


def _read_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _all_packages_present(_module_name):
    return object()


def _ready_cli_discovery() -> FeatureDiscovery:
    return FeatureDiscovery(features=[
        FeatureInfo(
            feature_id="web_research",
            name="Web Research",
            description="Ready research backend",
            enabled=False,
            ready=True,
            missing_setup=[],
            install_commands=[],
            config_flag="enable_research",
        ),
        FeatureInfo(
            feature_id="notebook_sync",
            name="NotebookLM Sync",
            description="Ready notebook integration",
            enabled=False,
            ready=True,
            missing_setup=[],
            install_commands=[],
            config_flag="enable_notebook_sync",
        ),
    ])


def _write_cli_preflight_decisions(tmpdir: str) -> str:
    path = Path(tmpdir) / "preflight_decisions.json"
    path.write_text(json.dumps({
        "confirmed_by_user": True,
        "install_decisions": {},
        "feature_decisions": {
            "web_research": "skip",
            "notebook_sync": "skip",
        },
    }), encoding="utf-8")
    return str(path)


def _state_with_output(tmpdir: str, files: list[str]) -> ReportState:
    return ReportState.new("write an academic report", files, str(Path(tmpdir) / "out"))


def _prepare(tmpdir: str, family: str = "academic_paper") -> ReportState:
    src = Path(tmpdir) / "source.txt"
    src.write_text(
        "The pilot program enrolled 42 participants and the data show a 20 percent processing-time reduction.",
        encoding="utf-8",
    )
    with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
        return prepare_workflow(
            f"write a {family}",
            [str(src)],
            str(Path(tmpdir) / "out"),
            report_profile=family,
        )


def _write_agent_artifacts(state: ReportState) -> None:
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    evidence_id = _read_jsonl(state.sources["evidence_ledger_path"])[0]["evidence_id"]
    claim_matrix = {
        "claims": [{
            "claim_id": "c1",
            "claim_text": "The data show 42 participants.",
            "claim_type": "statistical",
            "risk_level": "low",
            "status": "supported",
            "evidence_ids": [evidence_id],
            "requires_hedged_wording": False,
            "claim_role": "primary",
        }]
    }
    (run_dir / "claim_matrix.json").write_text(json.dumps(claim_matrix), encoding="utf-8")

    sections = {
        section_id: {
            "section_id": section_id,
            "goals": f"Cover {section_id}",
            "claim_ids": [] if section_id in {"references", "appendix"} else ["c1"],
            "paragraph_order": ["summarize the supported claim"],
            "figure_ids": [],
        }
        for section_id in state.plan["blueprint"]["section_order"]
    }
    (run_dir / "outline.json").write_text(json.dumps({"sections": sections}), encoding="utf-8")

    section_dir = run_dir / "section_drafts"
    section_dir.mkdir(exist_ok=True)
    sentence_rows = []
    for section_id in state.plan["blueprint"]["section_order"]:
        if section_id in {"references", "appendix"}:
            text = f"# {section_id.title()}\n\nReference material is listed in the generated references section."
            claims = []
            evidence = []
            citations = []
        else:
            text = f"# {section_id.title()}\n\nThe pilot program enrolled 42 participants [CITE:{evidence_id}]."
            claims = ["c1"]
            evidence = [evidence_id]
            citations = [evidence_id]
        (section_dir / f"{section_id}.md").write_text(text, encoding="utf-8")
        if claims:
            sentence_rows.append({
                "sentence_id": f"sent_{len(sentence_rows)}",
                "section_id": section_id,
                "claim_ids": claims,
                "evidence_ids": evidence,
                "citation_ids": citations,
                "wording_strength": "hedged",
                "draft_origin": "agent_draft",
            })
    with open(run_dir / "sentence_map.jsonl", "w", encoding="utf-8") as f:
        for row in sentence_rows:
            f.write(json.dumps(row) + "\n")


class SourcePipelineTests(unittest.TestCase):
    def test_absolute_txt_source_is_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("This source records 42 participants and a 20 percent reduction.", encoding="utf-8")

            state = _state_with_output(tmpdir, [str(src)])
            state = run_corpus_build(state)
            state = run_source_parse(state)

            entry = state.sources["source_registry"][0]
            self.assertEqual(entry["file_path"], str(src.resolve()))
            self.assertEqual(entry["parse_status"], "parsed")
            self.assertTrue(entry["parsed_content"])
            self.assertTrue(Path(state.sources["source_registry_path"]).exists())

    def test_missing_source_hard_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state_with_output(tmpdir, [str(Path(tmpdir) / "missing.txt")])
            with self.assertRaises(QAHardBlockError):
                run_corpus_build(state)

    def test_table_only_csv_produces_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "data.csv"
            src.write_text(
                "metric,value,notes\nparticipants,42,pilot program enrollment count\n",
                encoding="utf-8",
            )
            state = _state_with_output(tmpdir, [str(src)])
            state = run_corpus_build(state)
            state = run_source_parse(state)
            state = run_evidence_normalize(state)
            state = run_evidence_store(state)

            evidence = _read_jsonl(state.sources["evidence_ledger_path"])
            self.assertTrue(evidence)
            self.assertEqual(evidence[0]["source_file_name"], "data.csv")

    def test_toml_source_is_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "pyproject.toml"
            src.write_text(
                "[project]\nname = \"demo\"\nversion = \"0.1.0\"\n",
                encoding="utf-8",
            )
            state = _state_with_output(tmpdir, [str(src)])
            state = run_corpus_build(state)
            state = run_source_parse(state)

            entry = state.sources["source_registry"][0]
            self.assertEqual(entry["parse_status"], "parsed")
            self.assertTrue(entry["parsed_content"])

    def test_docx_source_is_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.docx"
            doc = Document()
            doc.add_paragraph("The pilot program enrolled 42 participants.")
            doc.save(src)

            state = _state_with_output(tmpdir, [str(src)])
            state = run_corpus_build(state)
            state = run_source_parse(state)

            self.assertEqual(state.sources["source_registry"][0]["parse_status"], "parsed")

    def test_unsupported_parser_fallback_does_not_fake_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.unknownext"
            src.write_text("This file has enough text but no supported parser.", encoding="utf-8")
            state = _state_with_output(tmpdir, [str(src)])
            state = run_corpus_build(state)

            with self.assertRaises(QAHardBlockError) as ctx:
                run_source_parse(state)
        self.assertIn("agent fallback parser is not implemented", str(ctx.exception))

    def test_methods_protocol_preserves_non_graph_project_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new(
                "Write a graduate admissions project introduction.",
                [],
                str(Path(tmpdir) / "out"),
            )
            state.spec["report_profile"] = "admissions_project_report"
            run_dir = Path(state.output["run_dir"])
            methods_path = run_dir / "section_drafts" / "methods.md"
            methods_path.parent.mkdir(exist_ok=True)
            original = (
                "# Methods\n\n"
                "## Overall System Architecture\n\n"
                "I built a shared decision core for Taiwan equities validation.\n\n"
                "## Historical Replay and Evidence Artifacts\n\n"
                "I implemented day-by-day replay outputs.\n"
            )
            methods_path.write_text(original, encoding="utf-8")
            state.drafts["section_drafts"] = {"methods": str(methods_path)}

            result = run_methods_protocol_build(state)

            self.assertEqual(methods_path.read_text(encoding="utf-8"), original)
            protocol = Path(result.drafts["methods_protocol"]).read_text(encoding="utf-8")
            self.assertIn("Overall System Architecture", protocol)
            self.assertNotIn("Graph Construction", protocol)

    def test_methods_protocol_is_idempotent_for_existing_protocol_headings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new(
                "Write a knowledge graph analysis report.",
                [],
                str(Path(tmpdir) / "out"),
            )
            run_dir = Path(state.output["run_dir"])
            methods_path = run_dir / "section_drafts" / "methods.md"
            methods_path.parent.mkdir(exist_ok=True)
            original = (
                "# Methods\n\n"
                "## Graph Construction\n\n"
                "We built graph nodes and edges from source documents.\n\n"
                "## Validation Procedure\n\n"
                "We checked graph consistency.\n"
            )
            methods_path.write_text(original, encoding="utf-8")
            state.drafts["section_drafts"] = {"methods": str(methods_path)}

            run_methods_protocol_build(state)
            first = methods_path.read_text(encoding="utf-8")
            run_methods_protocol_build(state)
            second = methods_path.read_text(encoding="utf-8")

            self.assertEqual(first, second)
            self.assertEqual(second.count("## Graph Construction"), 1)


class StageWorkflowTests(unittest.TestCase):
    def test_prepare_creates_evidence_and_agent_task_briefs_without_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir)

            self.assertEqual(state.status, "awaiting_agent_artifacts")
            self.assertTrue(Path(state.spec["report_spec_path"]).exists())
            self.assertTrue(Path(state.plan["blueprint_path"]).exists())
            self.assertTrue(Path(state.sources["evidence_ledger_path"]).exists())
            tasks_dir = Path(state.runtime["agent_tasks_dir"])
            self.assertTrue((tasks_dir / "01_claim_plan.md").exists())
            self.assertTrue((tasks_dir / "02_outline_plan.md").exists())
            self.assertTrue((tasks_dir / "03_section_draft.md").exists())

    def test_validate_requires_missing_claim_matrix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir)

            with self.assertRaises(AgentWorkRequired) as ctx:
                validate_workflow(state.job_id)

            self.assertIn("claim_matrix.json", ctx.exception.missing_artifacts[0])
            resumed = status_workflow(state.job_id)
            self.assertEqual(resumed.status, "awaiting_agent_artifacts")

    def test_malformed_claim_matrix_hard_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir)
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            (run_dir / "claim_matrix.json").write_text("{bad json", encoding="utf-8")

            with self.assertRaises(QAHardBlockError) as ctx:
                validate_workflow(state.job_id)
            self.assertIn("Malformed claim_matrix.json", str(ctx.exception))

    def test_full_staged_agent_artifact_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, "business_report")
            _write_agent_artifacts(state)

            validated = validate_workflow(state.job_id)
            self.assertEqual(validated.status, "validated")
            self.assertEqual(validated.qa["qa_decision"], "pass")

            rendered = render_workflow(state.job_id)
            self.assertEqual(rendered.status, "completed")
            self.assertTrue((Path(rendered.output["run_dir"]) / "final.docx").exists())
            roles = {
                item["role"]
                for item in json.loads(Path(rendered.output["artifacts_manifest_path"]).read_text(encoding="utf-8"))["files"]
            }
            self.assertIn("qa_qa_summary", roles)
            self.assertIn("evidence_sentence_map", roles)
            self.assertIn("traceability_claim_to_source_audit", roles)

    def test_run_convenience_stops_for_agent_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants and a 20 percent reduction.", encoding="utf-8")
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                with self.assertRaises(AgentWorkRequired):
                    run_workflow("write an academic report", [str(src)], str(Path(tmpdir) / "out"))

    def test_prepare_persists_optional_feature_flags_before_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants.", encoding="utf-8")
            workspace = str(Path(tmpdir) / "out")
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present), \
                 patch("report_workflow.nodes.notebook_sync.notebooklm_available", return_value=False):
                state = prepare_workflow(
                    "write a work report",
                    [str(src)],
                    workspace,
                    report_profile="business_report",
                    enable_research=True,
                    enable_notebook_sync=True,
                    notebooklm_notebook_id="notebook-123",
                )

            resumed = status_workflow(state.job_id, workspace_root=workspace)
            self.assertTrue(resumed.flags["enable_research"])
            self.assertTrue(resumed.flags["enable_notebook_sync"])
            self.assertEqual(resumed.spec["notebooklm_notebook_id"], "notebook-123")

    def test_outline_requires_required_blueprint_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, "academic_paper")
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_id = _read_jsonl(state.sources["evidence_ledger_path"])[0]["evidence_id"]
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "c1",
                    "claim_text": "The pilot program enrolled 42 participants.",
                    "claim_type": "statistical",
                    "status": "supported",
                    "evidence_ids": [evidence_id],
                    "claim_role": "primary",
                }]
            }), encoding="utf-8")
            (run_dir / "outline.json").write_text(json.dumps({
                "sections": {
                    "results": {
                        "section_id": "results",
                        "goals": "Cover results",
                        "claim_ids": ["c1"],
                        "paragraph_order": ["summary"],
                        "figure_ids": [],
                    }
                }
            }), encoding="utf-8")

            with self.assertRaises(QAHardBlockError) as ctx:
                validate_workflow(state.job_id)
            self.assertIn("missing required sections", str(ctx.exception))

    def test_sentence_map_rejects_unknown_section_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, "academic_paper")
            _write_agent_artifacts(state)
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_id = _read_jsonl(state.sources["evidence_ledger_path"])[0]["evidence_id"]
            (run_dir / "sentence_map.jsonl").write_text(json.dumps({
                "sentence_id": "sent_0",
                "section_id": "ghost",
                "claim_ids": ["c1"],
                "evidence_ids": [evidence_id],
                "citation_ids": [evidence_id],
            }) + "\n", encoding="utf-8")

            with self.assertRaises(QAHardBlockError) as ctx:
                validate_workflow(state.job_id)
            self.assertIn("unknown section", str(ctx.exception))

    def test_optional_appendix_is_not_required_when_omitted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir, "business_report")
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            evidence_id = _read_jsonl(state.sources["evidence_ledger_path"])[0]["evidence_id"]
            (run_dir / "claim_matrix.json").write_text(json.dumps({
                "claims": [{
                    "claim_id": "c1",
                    "claim_text": "The pilot program enrolled 42 participants.",
                    "claim_type": "statistical",
                    "status": "supported",
                    "evidence_ids": [evidence_id],
                }]
            }), encoding="utf-8")
            required_sections = ["executive_summary", "findings", "recommendations"]
            (run_dir / "outline.json").write_text(json.dumps({
                "sections": {
                    section_id: {
                        "section_id": section_id,
                        "goals": f"Cover {section_id}",
                        "claim_ids": ["c1"],
                        "paragraph_order": ["summary"],
                        "figure_ids": [],
                    }
                    for section_id in required_sections
                }
            }), encoding="utf-8")
            section_dir = run_dir / "section_drafts"
            section_dir.mkdir(exist_ok=True)
            for section_id in required_sections:
                (section_dir / f"{section_id}.md").write_text(
                    f"# {section_id.title()}\n\nThe pilot program enrolled 42 participants [CITE:{evidence_id}].",
                    encoding="utf-8",
                )
            with open(run_dir / "sentence_map.jsonl", "w", encoding="utf-8") as f:
                for index, section_id in enumerate(required_sections):
                    f.write(json.dumps({
                        "sentence_id": f"sent_{index}",
                        "section_id": section_id,
                        "claim_ids": ["c1"],
                        "evidence_ids": [evidence_id],
                        "citation_ids": [evidence_id],
                    }) + "\n")

            validated = validate_workflow(state.job_id)
            self.assertEqual(validated.qa["qa_decision"], "pass")
            self.assertNotIn("appendix", validated.drafts["section_drafts"])


class CLITests(unittest.TestCase):
    def test_cli_prepare_validate_render_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants and a 20 percent reduction.", encoding="utf-8")
            decisions_path = _write_cli_preflight_decisions(tmpdir)
            stdout = io.StringIO()
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present), \
                 patch("report_workflow.cli.check_preflight", return_value=PreflightResult(ok=True, missing_packages=[])), \
                 patch("report_workflow.cli.discover_features", return_value=_ready_cli_discovery()), \
                 patch("sys.stdout", stdout):
                code = cli_main([
                    "prepare",
                    "--prompt", "write a work report",
                    "--source", str(src),
                    "--output", str(Path(tmpdir) / "out"),
                    "--profile", "business_report",
                    "--preflight-decisions", decisions_path,
                ])
            self.assertEqual(code, 0)
            job_id = next(line.split(": ", 1)[1] for line in stdout.getvalue().splitlines() if line.startswith("job_id:"))

            state = status_workflow(job_id)
            _write_agent_artifacts(state)

            with patch("sys.stdout", io.StringIO()) as validate_out:
                self.assertEqual(cli_main(["validate", "--job-id", job_id]), 0)
                self.assertIn("status: validated", validate_out.getvalue())

            with patch("sys.stdout", io.StringIO()) as render_out:
                self.assertEqual(cli_main(["render", "--job-id", job_id]), 0)
                self.assertIn("status: completed", render_out.getvalue())

            with patch("sys.stdout", io.StringIO()) as status_out:
                self.assertEqual(cli_main(["status", "--job-id", job_id]), 0)
                self.assertIn("final_docx_path:", status_out.getvalue())

    def test_cli_prepare_requires_preflight_decision_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants.", encoding="utf-8")
            stderr = io.StringIO()
            with patch("report_workflow.cli.check_preflight", return_value=PreflightResult(ok=True, missing_packages=[])), \
                 patch("report_workflow.cli.discover_features", return_value=_ready_cli_discovery()), \
                 patch("sys.stderr", stderr):
                code = cli_main([
                    "prepare",
                    "--prompt", "write a work report",
                    "--source", str(src),
                    "--output", str(Path(tmpdir) / "out"),
                    "--profile", "business_report",
                ])
            self.assertEqual(code, 3)
            self.assertIn("missing preflight_decisions", stderr.getvalue())

    def test_cli_prepare_malformed_preflight_decisions_returns_user_decision_exit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants.", encoding="utf-8")
            bad_decisions = Path(tmpdir) / "bad_decisions.json"
            bad_decisions.write_text("[]", encoding="utf-8")
            stderr = io.StringIO()
            with patch("report_workflow.cli.check_preflight", return_value=PreflightResult(ok=True, missing_packages=[])), \
                 patch("report_workflow.cli.discover_features", return_value=_ready_cli_discovery()), \
                 patch("sys.stderr", stderr):
                code = cli_main([
                    "prepare",
                    "--prompt", "write a work report",
                    "--source", str(src),
                    "--output", str(Path(tmpdir) / "out"),
                    "--profile", "business_report",
                    "--preflight-decisions", str(bad_decisions),
                ])
            self.assertEqual(code, 3)
            self.assertIn("invalid preflight_decisions file", stderr.getvalue())

    def test_cli_prepare_blocks_required_dependency_until_preflight_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants.", encoding="utf-8")
            decisions = Path(tmpdir) / "preflight_decisions.json"
            decisions.write_text(json.dumps({
                "confirmed_by_user": True,
                "install_decisions": {
                    "python_packages": "installed",
                },
                "feature_decisions": {
                    "web_research": "skip",
                    "notebook_sync": "skip",
                },
            }), encoding="utf-8")
            stderr = io.StringIO()
            with patch(
                "report_workflow.cli.check_preflight",
                return_value=PreflightResult(ok=False, missing_packages=["pydantic"]),
            ), \
                 patch("report_workflow.cli.discover_features", return_value=_ready_cli_discovery()), \
                 patch("sys.stderr", stderr):
                code = cli_main([
                    "prepare",
                    "--prompt", "write a work report",
                    "--source", str(src),
                    "--output", str(Path(tmpdir) / "out"),
                    "--profile", "business_report",
                    "--preflight-decisions", str(decisions),
                ])
            self.assertEqual(code, 3)
            self.assertIn("Required dependencies", stderr.getvalue())

    def test_cli_prepare_requires_accept_degraded_decision_for_degraded_render(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants.", encoding="utf-8")
            decisions = Path(tmpdir) / "preflight_decisions.json"
            decisions.write_text(json.dumps({
                "confirmed_by_user": True,
                "install_decisions": {
                    "pandoc": "install",
                },
                "feature_decisions": {
                    "web_research": "skip",
                    "notebook_sync": "skip",
                },
            }), encoding="utf-8")
            preflight = PreflightResult(
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
            stderr = io.StringIO()
            with patch("report_workflow.cli.check_preflight", return_value=preflight), \
                 patch("report_workflow.cli.discover_features", return_value=_ready_cli_discovery()), \
                 patch("sys.stderr", stderr):
                code = cli_main([
                    "prepare",
                    "--prompt", "write a work report",
                    "--source", str(src),
                    "--output", str(Path(tmpdir) / "out"),
                    "--profile", "business_report",
                    "--preflight-decisions", str(decisions),
                    "--allow-degraded-render",
                ])
            self.assertEqual(code, 3)
            self.assertIn("accept_degraded", stderr.getvalue())

    def test_default_workspace_root_is_project_local_even_if_cwd_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants and a 20 percent reduction.", encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(tmpdir)
                with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                    state = prepare_workflow(
                        "write a work report",
                        [str(src)],
                        None,
                        report_profile="business_report",
                    )
                self.assertEqual(default_workspace_root(), PROJECT_ROOT / "output")
                self.assertTrue(Path(state.output["run_dir"]).is_relative_to(PROJECT_ROOT / "output"))
            finally:
                os.chdir(original_cwd)

    def test_relative_workspace_override_is_resolved_from_project_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants and a 20 percent reduction.", encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                import os
                os.chdir(tmpdir)
                with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                    state = prepare_workflow(
                        "write a work report",
                        [str(src)],
                        "custom-out",
                        report_profile="business_report",
                    )
                self.assertTrue(Path(state.output["run_dir"]).is_relative_to(PROJECT_ROOT / "custom-out"))
            finally:
                os.chdir(original_cwd)

    def test_custom_workspace_run_can_resume_without_shared_index_when_root_is_provided(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir) / "isolated-workspace"
            src = Path(tmpdir) / "source.txt"
            src.write_text("The data show 42 participants and a 20 percent reduction.", encoding="utf-8")
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                state = prepare_workflow(
                    "write a work report",
                    [str(src)],
                    str(workspace_root),
                    report_profile="business_report",
                )
            clear_job_run_hints()
            resumed = status_workflow(state.job_id, workspace_root=str(workspace_root))
            self.assertEqual(Path(resumed.output["workspace_root"]), workspace_root.resolve())
            self.assertEqual(Path(resumed.output["run_dir"]), Path(state.output["run_dir"]).resolve())


class GateTests(unittest.TestCase):
    def test_claim_without_evidence_is_blocked(self):
        claim_matrix = {"claims": [{"claim_id": "c1", "claim_text": "Unsupported", "claim_type": "factual", "evidence_ids": []}]}
        results = run_factuality_check_fa([], claim_matrix, [])
        self.assertEqual(results[0]["status"], "blocked")

    def test_statistical_claim_requires_quantitative_evidence(self):
        claim_matrix = {"claims": [{"claim_id": "c1", "claim_text": "Reduced by 20 percent.", "claim_type": "statistical", "evidence_ids": ["e1"]}]}
        sentence_map = [{"claim_ids": ["c1"], "evidence_ids": ["e1"]}]
        evidence = [{"evidence_id": "e1", "evidence_type": "qualitative"}]
        fa = run_factuality_check_fa(sentence_map, claim_matrix, evidence)
        fb = run_factuality_check_fb(fa, claim_matrix, evidence)
        self.assertEqual(fb[0]["status"], "blocked")

    def test_factuality_blocks_non_publishable_claim_status(self):
        claim_matrix = {"claims": [{"claim_id": "c1", "claim_text": "Claim", "status": "disputed", "evidence_ids": ["e1"]}]}
        results = run_factuality_check_fa([{"claim_ids": ["c1"], "evidence_ids": ["e1"]}], claim_matrix, [{"evidence_id": "e1"}])
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIn("not publishable", results[0]["reason"])

    def test_factuality_blocks_unknown_sentence_map_evidence(self):
        claim_matrix = {"claims": [{"claim_id": "c1", "claim_text": "Claim", "evidence_ids": ["e1"]}]}
        results = run_factuality_check_fa([{"claim_ids": ["c1"], "evidence_ids": ["e2"]}], claim_matrix, [{"evidence_id": "e1"}])
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIn("Sentence map references unknown evidence", results[0]["reason"])

    def test_factuality_blocks_claim_type_not_allowed_by_evidence(self):
        claim_matrix = {"claims": [{"claim_id": "c1", "claim_text": "Claim", "claim_type": "statistical", "evidence_ids": ["e1"]}]}
        evidence = [{"evidence_id": "e1", "evidence_type": "qualitative", "allowed_claim_types": ["factual"]}]
        results = run_factuality_check_fa([{"claim_ids": ["c1"], "evidence_ids": ["e1"]}], claim_matrix, evidence)
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIn("not allowed", results[0]["reason"])

    def test_factuality_does_not_match_units_by_substring(self):
        claim_matrix = {
            "claims": [{
                "claim_id": "c1",
                "claim_text": "The displacement was 5 m.",
                "claim_type": "factual",
                "evidence_ids": ["e1"],
            }]
        }
        checked = [{"claim_id": "c1", "status": "verified", "checker": "FB", "reason": ""}]
        evidence = [{
            "evidence_id": "e1",
            "evidence_type": "quantitative",
            "content": "The displacement was 5 mm.",
        }]
        results = run_factuality_check_fe(checked, claim_matrix, evidence)
        self.assertEqual(results[0]["status"], "blocked")
        self.assertIn("not found", results[0]["reason"])

    def test_qa_gate_blocks_missing_citation_placeholder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.sources["source_registry"] = [{"parse_status": "parsed", "parsed_content": [{"content": "source text"}]}]
            evidence_path = Path(tmpdir) / "evidence.jsonl"
            evidence_path.write_text(json.dumps({"evidence_id": "e1", "evidence_type": "qualitative"}) + "\n", encoding="utf-8")
            state.sources["evidence_ledger_path"] = str(evidence_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
            state.plan["outline"] = {"sections": {"results": {"claim_ids": ["c1"]}}}
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nReal content without citation.", encoding="utf-8")
            section = Path(tmpdir) / "section.md"
            section.write_text("# Results\n\nReal content without citation.", encoding="utf-8")
            sentence_map = Path(tmpdir) / "sentence_map.jsonl"
            sentence_map.write_text(json.dumps({"claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n", encoding="utf-8")
            factuality = Path(tmpdir) / "factuality.json"
            factuality.write_text(json.dumps({"claims": [], "blocked_count": 0, "verified_count": 1}), encoding="utf-8")
            state.drafts.update({
                "merged_draft_md": str(merged),
                "section_drafts": {"results": str(section)},
                "sentence_map_path": str(sentence_map),
            })
            state.qa["factuality_report_path"] = str(factuality)

            with self.assertRaises(QAHardBlockError):
                run_qa_gate(state)
            self.assertIn("missing citation placeholders", "; ".join(state.qa["hard_fail_reasons"]))

    def test_qa_gate_rejects_bypass_flag(self):
        state = ReportState.new("report", [], "out")
        state.flags["bypass_qa_gate"] = True
        with self.assertRaises(QAHardBlockError) as ctx:
            run_qa_gate(state)
        self.assertIn("bypass_qa_gate is not allowed", str(ctx.exception))

    def test_render_rejects_bypass_flag_from_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.status = "validated"
            state.qa["qa_decision"] = "pass"
            state.flags["bypass_qa_gate"] = True
            state.checkpoint("VALIDATED")

            with self.assertRaises(QAHardBlockError) as ctx:
                render_workflow(state.job_id)
            self.assertIn("bypass_qa_gate", str(ctx.exception))

    def test_render_rejects_pass_without_qa_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.status = "validated"
            state.qa["qa_decision"] = "pass"
            state.checkpoint("VALIDATED")

            with self.assertRaises(QAHardBlockError) as ctx:
                render_workflow(state.job_id)
            self.assertIn("qa_summary", str(ctx.exception))

    def test_resume_render_phase_uses_same_render_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.status = "running"
            state.qa["qa_decision"] = "pass"
            state.checkpoint("STYLE_PASS")

            with self.assertRaises(QAHardBlockError) as ctx:
                resume_workflow(state.job_id)
            self.assertIn("qa_summary", str(ctx.exception))

    def test_revise_existing_sidecars_satisfy_citation_linkage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "academic_paper"
            state.spec["task_intent"] = "revise_existing"
            state.sources["source_registry"] = [{"parse_status": "parsed", "parsed_content": [{"content": "source text"}]}]
            evidence_path = Path(tmpdir) / "evidence.jsonl"
            evidence_entries = [
                {"evidence_id": f"e{i}", "source_role": "research_document", "evidence_type": "qualitative"}
                for i in range(5)
            ]
            with open(evidence_path, "w", encoding="utf-8") as f:
                for entry in evidence_entries:
                    f.write(json.dumps(entry) + "\n")
            state.sources["evidence_ledger_path"] = str(evidence_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
            state.plan["outline"] = {"sections": {"results": {"claim_ids": ["c1"]}}}
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nPublication text has no placeholder.", encoding="utf-8")
            section = Path(tmpdir) / "section.md"
            section.write_text("# Results\n\nPublication text has no placeholder.", encoding="utf-8")
            sentence_map = Path(tmpdir) / "sentence_map.jsonl"
            sentence_map.write_text(json.dumps({"claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n", encoding="utf-8")
            factuality = Path(tmpdir) / "factuality.json"
            factuality.write_text(json.dumps({"claims": [], "blocked_count": 0, "verified_count": 1}), encoding="utf-8")
            state.drafts.update({
                "merged_draft_md": str(merged),
                "section_drafts": {"results": str(section)},
                "sentence_map_path": str(sentence_map),
            })
            state.qa["factuality_report_path"] = str(factuality)

            result = run_qa_gate(state)
            self.assertEqual(result.qa["qa_decision"], "pass")
            self.assertTrue(result.citations["sidecar_traceability"]["fulfilled"])
            self.assertTrue(result.qa["citation_policy_warnings"])

    def test_unresolved_citation_hard_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.sources["source_registry"] = [{"parse_status": "parsed", "parsed_content": [{"content": "source text"}]}]
            evidence_path = Path(tmpdir) / "evidence.jsonl"
            evidence_path.write_text(json.dumps({"evidence_id": "e1", "evidence_type": "quantitative"}) + "\n", encoding="utf-8")
            state.sources["evidence_ledger_path"] = str(evidence_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
            state.plan["outline"] = {"sections": {"results": {"claim_ids": ["c1"]}}}
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nReal content [CITE:e1].", encoding="utf-8")
            section = Path(tmpdir) / "section.md"
            section.write_text("# Results\n\nReal content [CITE:e1].", encoding="utf-8")
            sentence_map = Path(tmpdir) / "sentence_map.jsonl"
            sentence_map.write_text(json.dumps({"claim_ids": ["c1"], "evidence_ids": ["e1"], "citation_ids": ["e1"]}) + "\n", encoding="utf-8")
            factuality = Path(tmpdir) / "factuality.json"
            factuality.write_text(json.dumps({"claims": [], "blocked_count": 0, "verified_count": 1}), encoding="utf-8")
            state.drafts.update({
                "merged_draft_md": str(merged),
                "section_drafts": {"results": str(section)},
                "sentence_map_path": str(sentence_map),
            })
            state.qa["factuality_report_path"] = str(factuality)
            state.citations["citation_audit"] = [{"cite_id": "missing", "evidence_ids": ["missing"], "resolved": False}]
            with self.assertRaises(QAHardBlockError):
                run_qa_gate(state)

    # ------------------------------------------------------------------
    # F2: Provenance-driven wording strength (FD checker)
    # ------------------------------------------------------------------
    def test_fd_low_grade_blocks_measured_wording(self):
        """low-grade evidence + wording_strength=measured -> blocked."""
        sentence_map = [
            {
                "sentence_id": "s1",
                "claim_ids": ["c1"],
                "evidence_ids": ["e1"],
                "wording_strength": "measured",
            }
        ]
        claim_matrix = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
        evidence_ledger = [
            {"evidence_id": "e1", "evidence_grade": "low", "evidence_type": "qualitative"}
        ]
        results = run_factuality_check_fd(sentence_map, claim_matrix, evidence_ledger)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "blocked")
        self.assertEqual(results[0]["checker"], "FD")
        self.assertIn("low", results[0]["reason"])

    def test_fd_medium_grade_allows_hedged(self):
        """medium-grade evidence + wording_strength=hedged -> ok (not blocked)."""
        sentence_map = [
            {
                "sentence_id": "s1",
                "claim_ids": ["c1"],
                "evidence_ids": ["e1"],
                "wording_strength": "hedged",
            }
        ]
        claim_matrix = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
        evidence_ledger = [
            {"evidence_id": "e1", "evidence_grade": "medium", "evidence_type": "qualitative"}
        ]
        results = run_factuality_check_fd(sentence_map, claim_matrix, evidence_ledger)
        blocked = [r for r in results if r["status"] == "blocked"]
        self.assertEqual(len(blocked), 0)

    def test_fd_high_grade_allows_measured(self):
        """high-grade evidence + wording_strength=measured -> ok."""
        sentence_map = [
            {
                "sentence_id": "s1",
                "claim_ids": ["c1"],
                "evidence_ids": ["e1"],
                "wording_strength": "measured",
            }
        ]
        claim_matrix = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
        evidence_ledger = [
            {"evidence_id": "e1", "evidence_grade": "high", "evidence_type": "quantitative"}
        ]
        results = run_factuality_check_fd(sentence_map, claim_matrix, evidence_ledger)
        blocked = [r for r in results if r["status"] == "blocked"]
        self.assertEqual(len(blocked), 0)

    def test_fd_unknown_wording_not_penalised(self):
        """wording_strength value not in {measured,hedged,weak} -> not blocked."""
        sentence_map = [
            {
                "sentence_id": "s1",
                "claim_ids": ["c1"],
                "evidence_ids": ["e1"],
                "wording_strength": "strong",  # not a valid value
            }
        ]
        claim_matrix = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
        evidence_ledger = [
            {"evidence_id": "e1", "evidence_grade": "low", "evidence_type": "qualitative"}
        ]
        results = run_factuality_check_fd(sentence_map, claim_matrix, evidence_ledger)
        blocked = [r for r in results if r["status"] == "blocked"]
        self.assertEqual(len(blocked), 0)

    def test_revise_existing_factuality_uses_sidecars_without_default_deep_audit(self):
        """revise_existing keeps FE/FD as advisory when sidecar linkage is complete."""
        state = ReportState.new("report", [], "out")
        state.job_id = f"test_revision_sidecars_{uuid.uuid4().hex}"
        register_job_run(state.job_id, state.output["run_dir"])
        state.spec["task_intent"] = "revise_existing"
        state.spec["report_profile"] = "academic_paper"
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        run_dir.mkdir(parents=True, exist_ok=True)

        claim_matrix = {
            "claims": [{
                "claim_id": "c1",
                "claim_text": "StrategyIR is a methodological architecture claim with terms absent from evidence.",
                "claim_type": "methodological",
                "status": "supported",
                "evidence_ids": ["e1"],
            }]
        }
        (run_dir / "claim_matrix.json").write_text(json.dumps(claim_matrix), encoding="utf-8")
        (run_dir / "outline.json").write_text(json.dumps({"sections": {"methods": {"claim_ids": ["c1"]}}}), encoding="utf-8")
        evidence_path = run_dir / "evidence_ledger.jsonl"
        evidence_path.write_text(json.dumps({
            "evidence_id": "e1",
            "source_role": "research_document",
            "evidence_type": "qualitative",
            "evidence_grade": "medium",
            "content": "Architecture documentation establishes the compiler boundary.",
        }) + "\n", encoding="utf-8")
        sentence_map_path = run_dir / "sentence_map.jsonl"
        sentence_map_path.write_text(json.dumps({
            "sentence_id": "s1",
            "section_id": "methods",
            "claim_ids": ["c1"],
            "evidence_ids": ["e1"],
            "wording_strength": "measured",
        }) + "\n", encoding="utf-8")

        state.sources["evidence_ledger_path"] = str(evidence_path)
        state.drafts["sentence_map_path"] = str(sentence_map_path)
        result = run_factuality_check(state)
        report = json.loads(Path(result.qa["factuality_report_path"]).read_text(encoding="utf-8"))
        self.assertEqual(report["blocked_count"], 0)
        self.assertTrue(report["revision_sidecar_mode"])
        self.assertTrue(report["sidecars_consumed"]["claim_matrix"])
        self.assertTrue(report["advisory"])

    # ------------------------------------------------------------------
    # F3: Style-lint rules: banned phrases
    # ------------------------------------------------------------------
    def test_banned_phrase_records_style_warning(self):
        """Academic banned phrase in merged draft is style lint, not QA hard fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "academic_paper"
            state.sources["source_registry"] = [
                {"parse_status": "parsed", "parsed_content": [{"content": "x"}]}
            ]
            evidence_path = Path(tmpdir) / "evidence.jsonl"
            with open(evidence_path, "w", encoding="utf-8") as f:
                for index in range(5):
                    f.write(json.dumps({
                        "evidence_id": f"e{index}",
                        "source_role": "research_document",
                        "evidence_type": "quantitative",
                    }) + "\n")
            state.sources["evidence_ledger_path"] = str(evidence_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
            state.plan["outline"] = {"sections": {"results": {"claim_ids": ["c1"]}}}
            merged = Path(tmpdir) / "merged.md"
            # "clearly" is an academic banned phrase; [CITE:e1] is needed so citation gate passes first
            merged.write_text("# Results\n\nClearly, the data shows [CITE:e1].\n", encoding="utf-8")
            section = Path(tmpdir) / "section.md"
            section.write_text("# Results\n\nClearly, the data shows [CITE:e1].\n", encoding="utf-8")
            sentence_map = Path(tmpdir) / "sentence_map.jsonl"
            sentence_map.write_text(
                json.dumps({"claim_ids": ["c1"], "evidence_ids": ["e1"], "citation_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            factuality = Path(tmpdir) / "factuality.json"
            factuality.write_text(
                json.dumps({"claims": [], "blocked_count": 0, "verified_count": 1}),
                encoding="utf-8",
            )
            state.drafts.update({
                "merged_draft_md": str(merged),
                "section_drafts": {"results": str(section)},
                "sentence_map_path": str(sentence_map),
            })
            state.qa["factuality_report_path"] = str(factuality)
            result = run_qa_gate(state)
            self.assertEqual(result.qa["qa_decision"], "pass")
            self.assertIn("banned phrases", "; ".join(result.qa["style_lint_warnings"]))

    def test_no_banned_phrase_passes(self):
        """No banned phrases in merged draft -> QA gate passes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], "out")
            state.spec["report_profile"] = "academic_paper"
            state.sources["source_registry"] = [
                {"parse_status": "parsed", "parsed_content": [{"content": "x"}]}
            ]
            evidence_path = Path(tmpdir) / "evidence.jsonl"
            # Fix #2: academic_paper requires >=10 evidence entries across 3 source roles
            ev_entries = (
                [  # 7 graph_analysis entries
                    {"evidence_id": f"g{i}", "source_role": "graph_analysis", "evidence_type": "qualitative"}
                    for i in range(7)
                ]
                + [  # 2 code_artifact entries
                    {"evidence_id": f"c{i}", "source_role": "code_artifact", "evidence_type": "qualitative"}
                    for i in range(2)
                ]
                + [  # 1 research_document entry
                    {"evidence_id": "r1", "source_role": "research_document", "evidence_type": "qualitative"}
                ]
            )
            with open(evidence_path, "w", encoding="utf-8") as f:
                for ev in ev_entries:
                    f.write(json.dumps(ev) + "\n")
            state.sources["evidence_ledger_path"] = str(evidence_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "evidence_ids": ["g0"]}]}
            state.plan["outline"] = {"sections": {"results": {"claim_ids": ["c1"]}}}
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nThe data show a significant result [CITE:g0].\n", encoding="utf-8")
            section = Path(tmpdir) / "section.md"
            section.write_text("# Results\n\nThe data show a significant result [CITE:g0].\n", encoding="utf-8")
            sentence_map = Path(tmpdir) / "sentence_map.jsonl"
            sentence_map.write_text(
                json.dumps({"claim_ids": ["c1"], "evidence_ids": ["g0"], "citation_ids": ["g0"]}) + "\n",
                encoding="utf-8",
            )
            factuality = Path(tmpdir) / "factuality.json"
            factuality.write_text(
                json.dumps({"claims": [], "blocked_count": 0, "verified_count": 1}),
                encoding="utf-8",
            )
            state.drafts.update({
                "merged_draft_md": str(merged),
                "section_drafts": {"results": str(section)},
                "sentence_map_path": str(sentence_map),
            })
            state.qa["factuality_report_path"] = str(factuality)
            result = run_qa_gate(state)
            self.assertEqual(result.qa["qa_decision"], "pass")

    def test_banned_phrase_respects_work_family(self):
        """Work report bans different phrases; 'obviously' is work-banned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.spec["report_profile"] = "business_report"
            state.sources["source_registry"] = [
                {"parse_status": "parsed", "parsed_content": [{"content": "x"}]}
            ]
            evidence_path = Path(tmpdir) / "evidence.jsonl"
            evidence_path.write_text(
                json.dumps({"evidence_id": "e1", "evidence_type": "quantitative"}) + "\n",
                encoding="utf-8",
            )
            state.sources["evidence_ledger_path"] = str(evidence_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "evidence_ids": ["e1"]}]}
            state.plan["outline"] = {"sections": {"results": {"claim_ids": ["c1"]}}}
            merged = Path(tmpdir) / "merged.md"
            # "obviously" is work-banned but not academic-banned; [CITE:e1] for citation gate
            merged.write_text("# Results\n\nObviously, the result is clear [CITE:e1].\n", encoding="utf-8")
            section = Path(tmpdir) / "section.md"
            section.write_text("# Results\n\nObviously, the result is clear [CITE:e1].\n", encoding="utf-8")
            sentence_map = Path(tmpdir) / "sentence_map.jsonl"
            sentence_map.write_text(
                json.dumps({"claim_ids": ["c1"], "evidence_ids": ["e1"], "citation_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            factuality = Path(tmpdir) / "factuality.json"
            factuality.write_text(
                json.dumps({"claims": [], "blocked_count": 0, "verified_count": 1}),
                encoding="utf-8",
            )
            state.drafts.update({
                "merged_draft_md": str(merged),
                "section_drafts": {"results": str(section)},
                "sentence_map_path": str(sentence_map),
            })
            state.qa["factuality_report_path"] = str(factuality)
            result = run_qa_gate(state)
            self.assertEqual(result.qa["qa_decision"], "pass")
            self.assertIn("obviously", "; ".join(result.qa["style_lint_warnings"]))


class GovernanceAndUtilityTests(unittest.TestCase):
    def test_preflight_no_longer_requires_api_key(self):
        with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
            result = check_preflight()
            self.assertTrue(result.ok)
            state = run_preflight_checks(ReportState.new("report", [], "out"))
            self.assertIn("preflight", state.runtime)

    def test_preflight_reports_missing_package(self):
        def find_spec(module_name):
            if module_name == "pydantic":
                return None
            return object()

        with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=find_spec):
            result = check_preflight()
        self.assertFalse(result.ok)
        self.assertEqual(result.missing_packages, ["pydantic"])

    def test_tracked_review_is_not_supported_in_local_mvp(self):
        state = ReportState.new("tracked changes report", [], "out")
        with self.assertRaises(QAHardBlockError) as ctx:
            run_intake(state)
        self.assertIn("fresh_doc", str(ctx.exception))

    def test_guideline_select_uses_keywords_and_family_defaults(self):
        state = ReportState.new("report", [], "out")
        state.spec["keywords"] = ["cross-sectional"]
        state.spec["report_profile"] = "academic_paper"
        state = run_guideline_select(state)
        self.assertEqual(state.spec["selected_guidelines"], ["STROBE"])

    def test_section_plan_freeze_blocks_uncovered_claim(self):
        state = ReportState.new("report", [], "out")
        state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "claim_text": "Claim", "evidence_ids": ["e1"]}]}
        state.plan["outline"] = {"sections": {"results": {"section_id": "results", "claim_ids": ["c2"]}}}
        with self.assertRaises(QAHardBlockError):
            run_section_plan_freeze(state)

    def test_artifacts_metadata_records_actual_qa_fields(self):
        state = ReportState.new("report", [], "out")
        state.job_id = f"test_metadata_{uuid.uuid4().hex}"
        state.qa["qa_decision"] = "pass"
        state.qa["artifact_completeness_status"] = "pass"
        state = run_artifacts(state)
        metadata = json.loads(Path(state.output["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["qa_decision"], "pass")


# ------------------------------------------------------------------
# F1: Consistency Check integration tests
# ------------------------------------------------------------------

class ConsistencyCheckTests(unittest.TestCase):
    def test_numeric_contradiction_hard_fails(self):
        """Same unit (%%) appears with same value but different notation -> hard_fail (notation_inconsistency).

        Note: The consistency checker flags SAME value written with different notation
        (e.g. "20%" vs "20 percent") as notation_inconsistency, because the semantic
        content is identical but the representation differs.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            # "20%" and "20 percent" = SAME value, DIFFERENT notation -> notation_inconsistency
            merged.write_text(
                "# Results\n\nThe response rate was 20%.\n"
                "# Discussion\n\nA 20 percent response rate was observed.\n",
                encoding="utf-8",
            )
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {
                "claims": [{"claim_id": "c1", "claim_text": "The response rate was 20%.", "evidence_ids": ["e1"]}]
            }
            with self.assertRaises(QAHardBlockError) as ctx:
                run_consistency_check(state)
            # The checker raises one combined hard-fail with [numeric] and [units] tags
            self.assertIn("[numeric]", str(ctx.exception))

    def test_numeric_no_contradiction_passes(self):
        """Same number appears consistently -> no numeric issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            merged.write_text(
                "# Results\n\nThe pilot enrolled 42 participants.\n"
                "# Discussion\n\nAll 42 participants completed the study.\n",
                encoding="utf-8",
            )
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {
                "claims": [{"claim_id": "c1", "claim_text": "42 participants", "evidence_ids": ["e1"]}]
            }
            result = run_consistency_check(state)
            report = json.loads(Path(result.qa["consistency_report_path"]).read_text(encoding="utf-8"))
            high = [i for i in report["issues"] if i["severity"] == "high"]
            numeric_high = [i for i in high if i["check"] == "numeric"]
            self.assertEqual(len(numeric_high), 0)

    def test_unit_notation_inconsistency_hard_fails(self):
        """Same unit written as '%' and 'percent' -> high severity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            merged.write_text(
                "# Results\n\nThe response rate was 20%.\n"
                "# Discussion\n\nA 20 percent response rate was observed.\n",
                encoding="utf-8",
            )
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "claim_text": "response rate", "evidence_ids": ["e1"]}]}
            with self.assertRaises(QAHardBlockError) as ctx:
                run_consistency_check(state)
            self.assertIn("written multiple ways", str(ctx.exception))

    def test_unit_notation_consistent_passes(self):
        """'%' used consistently throughout -> no unit issue."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            merged.write_text(
                "# Results\n\nThe response rate was 20%.\n"
                "# Discussion\n\nA 20% response rate was observed.\n",
                encoding="utf-8",
            )
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "claim_text": "response rate", "evidence_ids": ["e1"]}]}
            result = run_consistency_check(state)
            report = json.loads(Path(result.qa["consistency_report_path"]).read_text(encoding="utf-8"))
            high = [i for i in report["issues"] if i["severity"] == "high"]
            self.assertEqual(len(high), 0)

    def test_missing_merged_draft_skips_gracefully(self):
        """No merged draft path -> skips, doesn't crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            state.drafts["merged_draft_md"] = ""
            state.drafts["sentence_map_path"] = ""
            state.plan["claim_matrix"] = {"claims": []}
            result = run_consistency_check(state)
            self.assertEqual(result.qa.get("consistency_report_path"), "")

    def test_numeric_20_vs_20point0_no_false_positive(self):
        """'20' and '20.0' are the same number -> no contradiction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            # Same unit (%) with "20" and "20.0" -> these are the same value
            merged.write_text(
                "# Results\n\nThe yield was 20%.\n"
                "# Methods\n\nThe yield was 20.0%.\n",
                encoding="utf-8",
            )
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {
                "claims": [{"claim_id": "c1", "claim_text": "yield", "evidence_ids": ["e1"]}]
            }
            # Should NOT raise -> float("20") == float("20.0")
            result = run_consistency_check(state)
            report = json.loads(Path(result.qa["consistency_report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["high_severity"], 0)

    def test_consistency_report_written(self):
        """Consistency report JSON is written with expected fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nConsistent text.\n", encoding="utf-8")
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": ["c1"], "evidence_ids": []}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "claim_text": "Consistent text.", "evidence_ids": []}]}
            result = run_consistency_check(state)
            report = json.loads(Path(result.qa["consistency_report_path"]).read_text(encoding="utf-8"))
            self.assertIn("issues", report)
            self.assertIn("total_issues", report)
            self.assertIn("high_severity", report)
            self.assertEqual(report["job_id"], state.job_id)

    def test_consistency_high_severity_raises_hard_block(self):
        """Any high-severity consistency issue -> QAHardBlockError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            merged.write_text(
                "# Results\n\nThe result was 50%.\n# Discussion\n\nThe result was 55 percent.\n",
                encoding="utf-8",
            )
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": ["c1"], "evidence_ids": ["e1"]}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {"claims": [{"claim_id": "c1", "claim_text": "result", "evidence_ids": ["e1"]}]}
            with self.assertRaises(QAHardBlockError):
                run_consistency_check(state)

    def test_consistency_low_severity_passes(self):
        """No high-severity issues -> no hard block."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nAll results were consistent.\n", encoding="utf-8")
            sm_path = Path(tmpdir) / "sentence_map.jsonl"
            sm_path.write_text(
                json.dumps({"sentence_id": "s1", "claim_ids": [], "evidence_ids": []}) + "\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.drafts["sentence_map_path"] = str(sm_path)
            state.plan["claim_matrix"] = {"claims": []}
            result = run_consistency_check(state)
            # Report is always written; check it has no high-severity issues
            report = json.loads(Path(result.qa["consistency_report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["high_severity"], 0)


# ------------------------------------------------------------------
# F7: Guideline Compliance Check tests
# ------------------------------------------------------------------

class GuidelineCheckTests(unittest.TestCase):
    def test_prisma_hard_violation_hard_fails(self):
        """PRISMA hard item not found in draft -> QAHardBlockError."""
        state = ReportState.new("report", [], "out")
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            # PRISMA_1a requires "systematic review" or "meta-analysis" in title/abstract
            merged.write_text("# Title\n\nThis is a study.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)
            state.spec["selected_guidelines"] = ["PRISMA"]
            state.plan["outline"] = {"sections": {"title": {}, "abstract": {}}}
            with self.assertRaises(QAHardBlockError) as ctx:
                run_guideline_check(state)
            self.assertIn("PRISMA_1a", str(ctx.exception))

    def test_prisma_hard_item_found_passes(self):
        """PRISMA hard item with matching keywords found -> no hard fail.

        Uses _check_guideline directly (no full node) to avoid needing
        all PRISMA hard items satisfied simultaneously.
        """
        from report_workflow.nodes.guideline_check import _check_guideline
        guideline = {
            "guideline": "TEST",
            "items": [
                {
                    "item_id": "TEST_1",
                    "description": "Test item",
                    "required": True,
                    "severity": "hard",
                    "covers_sections": ["intro"],
                    "detection_hints": ["methodology"],
                }
            ],
        }
        sections = {"intro": "This methodology section explains the approach."}
        hard, soft, warn = _check_guideline(guideline, sections)
        self.assertEqual(len(hard), 0)  # found -> no hard violation

    def test_no_selected_guidelines_skips(self):
        """No selected guidelines -> passthrough."""
        state = ReportState.new("report", [], "out")
        state.spec["selected_guidelines"] = []
        result = run_guideline_check(state)
        self.assertEqual(result.qa.get("guideline_report_path", ""), "")

    def test_split_by_sections(self):
        text = "# Introduction\n\nBackground content.\n# Methods\n\nMethod content.\n# Results\n\nResult content.\n"
        sections = _split_by_sections(text)
        self.assertIn("introduction", sections)
        self.assertIn("methods", sections)
        self.assertIn("results", sections)
        self.assertNotIn("Introduction", sections)  # keys are lowercase

    def test_guideline_report_written_on_check(self):
        """When guidelines are selected, report is written (even if hard violations exist).

        The report is written before the QAHardBlockError is raised,
        so we can verify the path is set regardless of pass/fail outcome.
        """
        state = ReportState.new("report", [], "out")
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Title\n\nStudy title.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)
            state.spec["selected_guidelines"] = ["PRISMA"]
            state.plan["outline"] = {"sections": {"title": {}}}
            # Expect hard violation -> but report should still be written first
            with self.assertRaises(QAHardBlockError):
                run_guideline_check(state)
            # Check report was written despite the exception
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            self.assertTrue((run_dir / "guideline_report.json").exists())


# ------------------------------------------------------------------
# F8: Figure Contract Check tests
# ------------------------------------------------------------------

class FigureContractCheckTests(unittest.TestCase):
    def _write_figure_recommendations(
        self,
        state: ReportState,
        recommendation_ids: list[str],
        write_plan: bool = True,
    ) -> None:
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        section_dir = run_dir / "section_drafts"
        section_dir.mkdir(parents=True, exist_ok=True)
        recommendations = [
            {
                "recommendation_id": figure_id,
                "evidence_ids": [f"E{index + 1}"],
                "recommended_figure_type": "bar",
                "section_id": "results",
            }
            for index, figure_id in enumerate(recommendation_ids)
        ]
        recommendations_path = run_dir / "figure_recommendations.json"
        recommendations_path.write_text(
            json.dumps({"recommendations": recommendations}),
            encoding="utf-8",
        )
        state.output["figure_recommendations_path"] = str(recommendations_path)
        if not write_plan:
            return
        figures = [
            {
                "figure_id": figure_id,
                "figure_type": "bar",
                "recommendation_id": figure_id,
                "source_evidence_ids": [f"E{index + 1}"],
                "section_id": "results",
                "title": f"Figure {index + 1}",
                "data": {"labels": ["A"], "series": [{"name": "Value", "values": [1]}]},
            }
            for index, figure_id in enumerate(recommendation_ids)
        ]
        (section_dir / "figure_plan.json").write_text(
            json.dumps({"figures": figures}),
            encoding="utf-8",
        )

    def test_figure_with_placeholder_prose_and_caption_passes(self):
        """All three contract elements present -> no issues."""
        text = "# Results\n\n[FIGURE:1]\n\nFigure 1: This is a chart.\n\nThe results are shown (see Figure 1).\n"
        issues = _check_figure_contract(text, ["1"])
        all_issues = [i for i in issues if i.get("issues")]
        self.assertEqual(len(all_issues), 0)

    def test_missing_caption_reported(self):
        """Figure placeholder but no caption -> soft issue."""
        text = "# Results\n\n[FIGURE:1]\n\nThe results are shown (see Figure 1).\n"
        issues = _check_figure_contract(text, ["1"])
        caption_issues = [
            j for i in issues
            for j in i.get("issues", [])
            if j.get("type") == "missing_caption"
        ]
        self.assertEqual(len(caption_issues), 1)

    def test_missing_prose_reference_reported(self):
        """Figure placeholder but no prose reference -> soft issue."""
        text = "# Results\n\n[FIGURE:1]\n\nFigure 1: This is a chart.\n"
        issues = _check_figure_contract(text, ["1"])
        prose_issues = [
            j for i in issues
            for j in i.get("issues", [])
            if j.get("type") == "missing_prose_reference"
        ]
        self.assertEqual(len(prose_issues), 1)

    def test_nonnumeric_figure_placeholder_with_caption_and_reference_passes(self):
        text = (
            "# Results\n\n"
            "[FIGURE:summary Voltage trend]\n\n"
            "Figure summary: Voltage trend.\n\n"
            "The measured trend is shown in Figure summary.\n"
        )
        issues = _check_figure_contract(text, ["summary"], hard_contract=True)
        all_issues = [i for i in issues if i.get("issues")]
        self.assertEqual(all_issues, [])

    def test_figure_contract_node_writes_report(self):
        """Figure contract node writes figure_contract_report.json."""
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "business_report"  # avoid academic hard table requirements
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\n[FIGURE:1]\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)
            state.plan["outline"] = {
                "sections": {"results": {"figure_ids": ["1"]}}
            }
            result = run_figure_quality(state)
            self.assertNotEqual(result.qa.get("figure_quality_report_path", ""), "")

    def test_figure_quality_warns_when_recommended_plan_is_unused(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "business_report"
        state.plan["outline"] = {"sections": {"results": {"figure_ids": []}}}
        self._write_figure_recommendations(state, ["figrec_1"])
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nNo figure is discussed here.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)

            result = run_figure_quality(state)
            report = json.loads(Path(result.qa["figure_quality_report_path"]).read_text(encoding="utf-8"))

        issue_types = {issue.get("type") for issue in report["issues"] if "type" in issue}
        self.assertIn("planned_figure_not_used", issue_types)
        self.assertIn("recommended_figure_plan_unused", issue_types)
        self.assertEqual(report["hard_issues"], [])

    def test_figure_quality_uses_run_dir_recommendations_when_state_path_missing(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "business_report"
        state.plan["outline"] = {"sections": {"results": {"figure_ids": []}}}
        self._write_figure_recommendations(state, ["figrec_1"])
        state.output.pop("figure_recommendations_path", None)
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nNo figure is discussed here.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)

            result = run_figure_quality(state)
            report = json.loads(Path(result.qa["figure_quality_report_path"]).read_text(encoding="utf-8"))

        issue_types = {issue.get("type") for issue in report["issues"] if "type" in issue}
        self.assertIn("planned_figure_not_used", issue_types)

    def test_figure_quality_warns_only_for_unused_recommended_planned_figures(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "business_report"
        state.plan["outline"] = {"sections": {"results": {"figure_ids": []}}}
        self._write_figure_recommendations(state, ["figrec_1", "figrec_2"])
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text(
                "# Results\n\n"
                "[FIGURE:figrec_1]\n\n"
                "Figure figrec_1: Used chart.\n\n"
                "The first chart is shown in Figure figrec_1.\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)

            result = run_figure_quality(state)
            report = json.loads(Path(result.qa["figure_quality_report_path"]).read_text(encoding="utf-8"))

        unused_ids = [
            issue.get("figure_id")
            for issue in report["issues"]
            if issue.get("type") == "planned_figure_not_used"
        ]
        summary_issues = [
            issue for issue in report["issues"]
            if issue.get("type") == "recommended_figure_plan_unused"
        ]
        self.assertEqual(unused_ids, ["figrec_2"])
        self.assertEqual(summary_issues, [])

    def test_figure_quality_skips_usage_lint_without_recommendations(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "business_report"
        state.plan["outline"] = {"sections": {"results": {"figure_ids": []}}}
        self._write_figure_recommendations(state, [])
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nNo figure is discussed here.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)

            result = run_figure_quality(state)
            report = json.loads(Path(result.qa["figure_quality_report_path"]).read_text(encoding="utf-8"))

        issue_types = {issue.get("type") for issue in report["issues"] if "type" in issue}
        self.assertNotIn("planned_figure_not_used", issue_types)

    def test_figure_quality_skips_usage_lint_when_plan_is_missing(self):
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "business_report"
        state.plan["outline"] = {"sections": {"results": {"figure_ids": []}}}
        self._write_figure_recommendations(state, ["figrec_1"], write_plan=False)
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text("# Results\n\nNo figure is discussed here.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)

            result = run_figure_quality(state)
            report = json.loads(Path(result.qa["figure_quality_report_path"]).read_text(encoding="utf-8"))

        issue_types = {issue.get("type") for issue in report["issues"] if "type" in issue}
        self.assertNotIn("planned_figure_not_used", issue_types)

    # ------------------------------------------------------------------
    # Fix #3: academic_paper flat hard issues must enter hard_issues
    # ------------------------------------------------------------------
    def test_no_audit_tables_in_academic_main_text_passes(self):
        """academic_paper with no forbidden markdown audit tables -> no issue raised."""
        state = ReportState.new("report", [], "out")
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            # Plain results text with no markdown audit tables
            merged.write_text("# Results\n\nSome results without tables.\n", encoding="utf-8")
            state.drafts["merged_draft_md"] = str(merged)
            state.plan["outline"] = {"sections": {"results": {}}}
            state.spec["report_profile"] = "academic_paper"
            # _check_no_audit_tables_in_main_text returns [] when no forbidden tables found
            issues = _check_no_audit_tables_in_main_text(
                merged.read_text(encoding="utf-8"), "academic_paper"
            )
            self.assertEqual(len(issues), 0)
            # run_figure_quality should not raise for plain text
            result = run_figure_quality(state)
            self.assertNotEqual(result.qa.get("figure_quality_report_path", ""), "")

    def test_academic_paper_table_found_passes(self):
        """academic_paper with all three required tables -> no hard issue."""
        state = ReportState.new("report", [], "out")
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            # Must include all three tables using inline content that matches the regex patterns:
            # 1. Graph metrics: "nodes" within 500 chars of "INFERRED" on same line
            # 2. Community contribution: "community" within 200 chars of "contribution" on same line
            # 3. Claim-evidence: "claim" within 300 chars of "evidence" on same line
            merged.write_text(
                "# Results\n\n"
                "Table 1: Graph Metrics: Nodes 500, Edges 1200, INFERRED 15%\n\n"
                "Table 2: Community Contributions: Community A maps to Core logic contribution role.\n\n"
                "Table 3: Claim-Evidence Matrix: Claim c1 is supported by evidence e1 and e2.\n\n"
                "# Discussion\n\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            state.plan["outline"] = {"sections": {"results": {}}}
            state.spec["report_profile"] = "academic_paper"
            result = run_figure_quality(state)
            # Should not raise
            self.assertNotEqual(result.qa.get("figure_quality_report_path", ""), "")


# ------------------------------------------------------------------
# figure_build node tests
# ------------------------------------------------------------------

class FigureBuildTests(unittest.TestCase):
    def test_missing_figure_plan_skips(self):
        """No figure_plan.json -> skips gracefully, no crash."""
        state = ReportState.new("report", [], "out")
        with tempfile.TemporaryDirectory() as tmpdir:
            section_drafts_dir = Path(tmpdir) / "section_drafts"
            section_drafts_dir.mkdir()
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            run_dir.mkdir(parents=True, exist_ok=True)
            # No figure_plan.json written
            result = run_figure_build(state)
            self.assertEqual(result.output.get("figure_manifest_path", ""), "")

    def test_malformed_figure_plan_skips(self):
        """Malformed figure_plan.json -> skips gracefully."""
        state = ReportState.new("report", [], "out")
        with tempfile.TemporaryDirectory() as tmpdir:
            section_drafts_dir = Path(tmpdir) / "section_drafts"
            section_drafts_dir.mkdir()
            plan_path = section_drafts_dir / "figure_plan.json"
            plan_path.write_text("not valid json{", encoding="utf-8")
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            run_dir.mkdir(parents=True, exist_ok=True)
            result = run_figure_build(state)
            self.assertEqual(result.output.get("figure_manifest_path", ""), "")

    def test_empty_figures_list_skips(self):
        """figure_plan.json with empty figures list -> skips gracefully."""
        state = ReportState.new("report", [], "out")
        with tempfile.TemporaryDirectory() as tmpdir:
            section_drafts_dir = Path(tmpdir) / "section_drafts"
            section_drafts_dir.mkdir()
            plan_path = section_drafts_dir / "figure_plan.json"
            plan_path.write_text(json.dumps({"figures": []}), encoding="utf-8")
            run_dir = WORKFLOW_RUNS_DIR / state.job_id
            run_dir.mkdir(parents=True, exist_ok=True)
            result = run_figure_build(state)
            self.assertEqual(result.output.get("figure_manifest_path", ""), "")


# ------------------------------------------------------------------
# topic_tags tests (via evidence_normalize)
# ------------------------------------------------------------------

class EvidenceNormalizeNewFieldsTests(unittest.TestCase):
    def test_topic_tags_extracted(self):
        """topic_tags are added to evidence entries."""
        from report_workflow.nodes.evidence_normalize import determine_topic_tags
        # statistical content
        tags = determine_topic_tags(
            "The results show a statistically significant reduction (p=0.003, t-test, 95% CI [2.1, 3.8])."
        )
        self.assertIn("statistical", tags)
        self.assertIn("results", tags)

    def test_topic_tags_multiple_match(self):
        """Multiple topic tags can match the same content."""
        from report_workflow.nodes.evidence_normalize import determine_topic_tags
        tags = determine_topic_tags(
            "The methodology used a randomised controlled trial comparing treatment versus control group outcomes."
        )
        self.assertIn("methods", tags)
        self.assertIn("comparative", tags)

    def test_topic_tags_no_match(self):
        """No keyword match -> empty list."""
        from report_workflow.nodes.evidence_normalize import determine_topic_tags
        tags = determine_topic_tags("The document was uploaded on 2024-01-01.")
        self.assertEqual(tags, [])

    def test_topic_tags_deduplicated(self):
        """Same tag matched by multiple keywords -> deduplicated."""
        from report_workflow.nodes.evidence_normalize import determine_topic_tags
        tags = determine_topic_tags(
            "The method methodology procedure protocol was used in this study."
        )
        # "method" and "methodology" both match "methods" tag
        self.assertEqual(tags.count("methods"), 1)


# ------------------------------------------------------------------
# Fix #1: parse_markdown and parse_code tests
# ------------------------------------------------------------------

class SourceParseNewTypesTests(unittest.TestCase):
    def test_parse_markdown_splits_blocks(self):
        """parse_markdown splits .md files into blocks with line_start/line_end."""
        from report_workflow.parsers.semi_structured_parser import parse_markdown
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.md"
            src.write_text(
                "# Introduction\n\n"
                "This is a paragraph.\n\n"
                "- item one\n"
                "- item two\n",
                encoding="utf-8",
            )
            result = parse_markdown(str(src))
            self.assertTrue(result["success"])
            self.assertTrue(len(result["blocks"]) >= 3)
            # Check metadata fields exist
            for block in result["blocks"]:
                self.assertIn("line_start", block)
                self.assertIn("line_end", block)
                self.assertIn("content_hash", block)
                self.assertIn("quote", block)
                self.assertEqual(block["source_file_path"], str(src))

    def test_parse_markdown_heading_has_quote(self):
        """Markdown heading block preserves full content as quote."""
        from report_workflow.parsers.semi_structured_parser import parse_markdown
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.md"
            src.write_text("# Introduction\n\nParagraph content.\n", encoding="utf-8")
            result = parse_markdown(str(src))
            heading_block = next(b for b in result["blocks"] if b["block_type"] == "heading")
            self.assertEqual(heading_block["quote"], "# Introduction")

    def test_parse_code_splits_python_class(self):
        """parse_code splits Python class/function definitions."""
        from report_workflow.parsers.code_parser import parse_code
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "example.py"
            src.write_text(
                "class MyClass:\n"
                "    def method(self):\n"
                "        pass\n"
                "\n"
                "def standalone():\n"
                "    return 42\n",
                encoding="utf-8",
            )
            result = parse_code(str(src))
            self.assertTrue(result["success"])
            self.assertTrue(len(result["blocks"]) >= 2)
            # At least one block should be a code_definition
            def_blocks = [b for b in result["blocks"] if b["block_type"] == "code_definition"]
            self.assertGreater(len(def_blocks), 0)
            for block in result["blocks"]:
                self.assertIn("line_start", block)
                self.assertIn("line_end", block)
                self.assertIn("content_hash", block)
                self.assertIn("source_file_path", block)
                self.assertEqual(block["source_file_path"], str(src))

    def test_parse_code_js_splits_function(self):
        """parse_code splits JavaScript function declarations."""
        from report_workflow.parsers.code_parser import parse_code
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "example.js"
            src.write_text(
                "function greet(name) {\n"
                "    return 'Hello, ' + name;\n"
                "}\n"
                "\n"
                "const add = (a, b) => a + b;\n",
                encoding="utf-8",
            )
            result = parse_code(str(src))
            self.assertTrue(result["success"])
            # Should have at least 1 code_definition block
            def_blocks = [b for b in result["blocks"] if b["block_type"] == "code_definition"]
            self.assertGreater(len(def_blocks), 0)

    def test_source_parse_handles_md_file_type(self):
        """source_parse routes .md files through parse_markdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.md"
            src.write_text("# Title\n\nParagraph content.\n", encoding="utf-8")
            state = _state_with_output(tmpdir, [str(src)])
            state = run_corpus_build(state)
            # file_type for .md should be "md"
            self.assertEqual(state.sources["source_registry"][0]["file_type"], "md")
            state = run_source_parse(state)
            self.assertEqual(state.sources["source_registry"][0]["parse_status"], "parsed")

    def test_source_parse_handles_py_file_type(self):
        """source_parse routes .py files through parse_code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "example.py"
            src.write_text(
                "class MyClass:\n"
                "    def method(self):\n"
                "        pass\n",
                encoding="utf-8",
            )
            state = _state_with_output(tmpdir, [str(src)])
            state = run_corpus_build(state)
            self.assertEqual(state.sources["source_registry"][0]["file_type"], "py")
            state = run_source_parse(state)
            self.assertEqual(state.sources["source_registry"][0]["parse_status"], "parsed")


# ------------------------------------------------------------------
# Fix #2: evidence_count >= 10 and diversity enforcement
# ------------------------------------------------------------------

class DiversityGateTests(unittest.TestCase):
    def test_evidence_count_below_5_hard_fails(self):
        """academic_paper with < 5 evidence entries -> hard fail."""
        from report_workflow.nodes.qa_gate import _source_diversity_reasons
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        # Create 3 evidence entries (below the new threshold of 5)
        evidence_entries = [
            {"evidence_id": f"e{i}", "source_role": "code_artifact"}
            for i in range(3)
        ]
        state.sources["evidence_ledger_path"] = ""
        state.plan["claim_matrix"] = {"claims": []}
        with patch("report_workflow.nodes.qa_gate._load_jsonl", return_value=evidence_entries):
            reasons = _source_diversity_reasons(state)
        self.assertTrue(any("5 evidence entries" in r for r in reasons))

    def test_academic_paper_all_primary_source_warns_without_code_artifact(self):
        """Missing code_artifact is advisory when docs can support architecture claims."""
        from report_workflow.nodes.qa_gate import _source_diversity_reasons
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        # 12 entries all primary_source -> no code_artifact role
        evidence_entries = [
            {"evidence_id": f"e{i}", "source_role": "primary_source"}
            for i in range(12)
        ]
        state.plan["claim_matrix"] = {"claims": []}
        with patch("report_workflow.nodes.qa_gate._load_jsonl", return_value=evidence_entries):
            reasons = _source_diversity_reasons(state)
        self.assertFalse(any("code_artifact" in r for r in reasons))
        self.assertTrue(any("code_artifact" in r for r in state.qa["evidence_policy_warnings"]))


# ------------------------------------------------------------------
# Fix #4: citation_bind double bracket fix
# ------------------------------------------------------------------

class CitationBindTests(unittest.TestCase):
    def test_resolve_citations_no_double_brackets(self):
        """graph_analysis citation resolved -> single brackets, not double."""
        evidence_ledger = [
            {
                "evidence_id": "g1",
                "source_id": "src_graph",
                "source_role": "graph_analysis",
                "source_file_name": "GRAPH_REPORT.md",
                "file_type": "md",
            }
        ]
        merged = "The graph shows [CITE:g1] analysis."
        resolved, audit = resolve_citations(merged, evidence_ledger, [])
        # Should NOT be [[Source: graphify:...]]
        self.assertNotIn("[[", resolved)
        # Should be [Source: graphify:GRAPH_REPORT.md]
        self.assertIn("[Source: graphify:GRAPH_REPORT.md]", resolved)

    def test_resolve_citations_code_artifact_no_double_brackets(self):
        """code_artifact citation resolved -> single brackets."""
        evidence_ledger = [
            {
                "evidence_id": "c1",
                "source_id": "src_code",
                "source_role": "code_artifact",
                "source_file_name": "model.py",
                "file_type": "py",
            }
        ]
        merged = "See [CITE:c1] for implementation."
        resolved, audit = resolve_citations(merged, evidence_ledger, [])
        self.assertNotIn("[[", resolved)
        self.assertIn("[Source: model.py]", resolved)

    def test_resolve_citations_research_document_apa(self):
        """research_document citation -> APA in brackets (already correct)."""
        evidence_ledger = [
            {
                "evidence_id": "r1",
                "source_id": "src_doc",
                "source_role": "research_document",
                "source_file_name": "paper.pdf",
                "file_type": "pdf",
            }
        ]
        merged = "Previous work [CITE:r1] shows..."
        resolved, audit = resolve_citations(merged, evidence_ledger, [])
        # APA citation is wrapped in [] by format_apa_citation; resolve wraps in [] again
        # So this will be [[Author, Year]] -> this is existing behavior for research_document
        # The Fix #4 only fixes code_artifact/graph_analysis which we already control
        self.assertNotIn("[[Source:", resolved)

    def test_internal_project_source_is_suppressed_in_publication_text(self):
        evidence_ledger = [
            {
                "evidence_id": "s1",
                "source_id": "src_local",
                "source_role": "internal_project_source",
                "source_file_name": "source_corpus.txt",
                "file_type": "txt",
            }
        ]
        merged = "The architecture is central [CITE:s1]."
        resolved, audit = resolve_citations(merged, evidence_ledger, [])
        self.assertNotIn("source & corpus", resolved.lower())
        self.assertNotIn("source_corpus", resolved.lower())


class MergeDraftNormalizationTests(unittest.TestCase):
    def test_canonicalize_section_content_removes_duplicate_headings(self):
        content = (
            "# Methods\n\n"
            "## Data Source and Corpus\n\n"
            "## Data Source and Corpus\n\n"
            "Text.\n\n"
            "# Research Methodology\n\n"
            "## Validation Procedure\n\n"
            "More text.\n"
        )
        normalized = _canonicalize_section_content("methods", content)
        self.assertEqual(normalized.count("## Data Source and Corpus"), 1)
        self.assertNotIn("\n# Research Methodology", "\n" + normalized)
        self.assertIn("## Research Methodology", normalized)


# ------------------------------------------------------------------
# Fix #5: results_mode reading order (outline first, then blueprint)
# ------------------------------------------------------------------

class ResultsModeTests(unittest.TestCase):
    def test_results_mode_from_outline_overrides_blueprint(self):
        """results_mode from outline takes priority over blueprint."""
        from report_workflow.nodes.qa_gate import _results_section_reasons
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        # Blueprint says empirical, but outline says architectural_characterization
        state.plan["blueprint"] = {
            "sections": {"results": {"results_mode": "empirical"}}
        }
        state.plan["outline"] = {
            "sections": {"results": {"results_mode": "architectural_characterization"}}
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text(
                "# Results\n\nThis is an architectural characterization "
                "without empirical performance data.\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            reasons = _results_section_reasons(state)
            # Should NOT warn about performance claims without numeric data
            # because architectural_characterization mode is active (from outline)
            no_warn = not any("performance claims" in r for r in reasons)
            self.assertTrue(no_warn)

    def test_results_mode_falls_back_to_blueprint(self):
        """When outline has no results_mode, blueprint is used."""
        from report_workflow.nodes.qa_gate import _results_section_reasons
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        state.plan["blueprint"] = {
            "sections": {"results": {"results_mode": "architectural_characterization"}}
        }
        state.plan["outline"] = {"sections": {"results": {}}}  # no results_mode key
        with tempfile.TemporaryDirectory() as tmpdir:
            merged = Path(tmpdir) / "merged.md"
            merged.write_text(
                "# Results\n\nThis is an architectural characterization.\n",
                encoding="utf-8",
            )
            state.drafts["merged_draft_md"] = str(merged)
            reasons = _results_section_reasons(state)
            # Should recognize architectural_characterization from blueprint
            no_warn = not any("performance claims" in r for r in reasons)
            self.assertTrue(no_warn)


if __name__ == "__main__":
    unittest.main()
