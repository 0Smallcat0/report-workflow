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
    def test_pasted_spreadsheet_table_becomes_a_table_block(self):
        """Copying a selection out of a spreadsheet yields tab-separated lines.

        It is the most common way a measurement table enters a notes file, and
        it used to be swallowed into the paragraph above it: no table_data, no
        chart, and the numbers graded as prose.
        """
        from report_workflow.parsers.semi_structured_parser import parse_markdown

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "notes.md"
            src.write_text(
                "今天量了一輪，結果如下\n"
                "流量\t冷側出口\t有效度\n"
                "2\t49.8\t0.709\n"
                "4\t48.1\t0.660\n"
                "\n"
                "之後再整理\n",
                encoding="utf-8",
            )
            blocks = parse_markdown(str(src))["blocks"]
            tables = [b for b in blocks if b["block_type"] == "table"]
            self.assertEqual(len(tables), 1, f"expected one table block: {blocks}")
            self.assertEqual(tables[0]["table_data"][0], ["流量", "冷側出口", "有效度"])
            self.assertEqual(len(tables[0]["table_data"]), 3)
            # The lead-in sentence keeps its own block rather than absorbing the table.
            paragraphs = [b for b in blocks if b["block_type"] == "paragraph"]
            self.assertTrue(any("今天量了一輪" in b["content"] for b in paragraphs))
            self.assertFalse(any("49.8" in b["content"] for b in paragraphs))

    def test_markdown_pipe_table_becomes_a_table_block(self):
        from report_workflow.parsers.semi_structured_parser import parse_markdown

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "notes.md"
            src.write_text(
                "| flow | outlet |\n| --- | --- |\n| 2 | 49.8 |\n| 4 | 48.1 |\n",
                encoding="utf-8",
            )
            tables = [b for b in parse_markdown(str(src))["blocks"]
                      if b["block_type"] == "table"]
            self.assertEqual(len(tables), 1)
            self.assertEqual(tables[0]["table_data"][0], ["flow", "outlet"])
            self.assertEqual(len(tables[0]["table_data"]), 3)

    def test_prose_containing_one_tab_stays_prose(self):
        """A run needs two rows of equal width, so a stray tab is not a table."""
        from report_workflow.parsers.semi_structured_parser import parse_markdown

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "notes.md"
            src.write_text("量測條件\t冷側 25 度，熱側 60 度。\n之後再確認定義。\n", encoding="utf-8")
            blocks = parse_markdown(str(src))["blocks"]
            self.assertFalse([b for b in blocks if b["block_type"] == "table"])

    def test_whole_table_block_counts_as_quantitative(self):
        """PDF, DOCX and markdown parsers all emit block_type "table".

        Only the single-row CSV shapes were listed, so a measurement table from
        any other source fell through to keyword matching and came out
        qualitative — which blocks statistical claims on the user's own data.
        """
        from report_workflow.nodes.evidence_normalize import determine_evidence_type

        rows = "流量\t冷側出口\t有效度\n2\t49.8\t0.709\n4\t48.1\t0.660"
        self.assertEqual(determine_evidence_type(rows, "table"), "quantitative")
        self.assertEqual(determine_evidence_type(rows, "csv_row"), "quantitative")

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

class MultipleUnreadableSourcesTests(unittest.TestCase):
    """One pass already knows about every unreadable attachment.

    Raising on the first meant an author with three of them discovered one per
    run: fix, resubmit, meet the next.
    """

    def _run(self, tmpdir, names):
        from report_workflow.nodes.source_parse import run_source_parse

        state = ReportState.new("report", [], str(Path(tmpdir) / "out"))
        registry = []
        for name in names:
            path = Path(tmpdir) / name
            path.write_text("", encoding="utf-8")
            registry.append({
                "file_name": name, "file_path": str(path),
                "file_type": name.rsplit(".", 1)[-1], "artifact_role": "source_data",
            })
        state.sources["source_registry"] = registry
        with self.assertRaises(QAHardBlockError) as ctx:
            run_source_parse(state)
        return str(ctx.exception)

    def test_every_unreadable_source_is_named_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            message = self._run(tmpdir, ["a.md", "b.md", "c.md"])
            for name in ("a.md", "b.md", "c.md"):
                self.assertIn(name, message)
            self.assertIn("3 sources", message)

    def test_a_single_failure_reads_naturally(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            message = self._run(tmpdir, ["only.md"])
            self.assertIn("only.md", message)
            self.assertNotIn("1 sources", message)


class SourceEncodingTests(unittest.TestCase):
    """Excel on a Traditional Chinese Windows machine writes Big5, not UTF-8.

    Every reader opened its file as UTF-8, so the default CSV export of this
    project's own target users failed at ingest with a raw codec error — in a
    pipeline that ships Chinese blueprints, CJK abstract scaling and GB/T
    citation formatting.
    """

    TEXT = "流量 (L/min),實測有效度\n2,0.709\n12,0.411\n"

    def _write(self, tmpdir, name, encoding):
        path = Path(tmpdir) / name
        path.write_bytes(self.TEXT.encode(encoding))
        return path

    def test_big5_is_decoded(self):
        from report_workflow.parsers.source_text import read_source_text

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write(tmpdir, "big5.csv", "big5")
            self.assertEqual(read_source_text(path), self.TEXT)

    def test_utf8_and_bom_are_unchanged(self):
        from report_workflow.parsers.source_text import read_source_text

        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(read_source_text(self._write(tmpdir, "a.csv", "utf-8")), self.TEXT)
            self.assertEqual(read_source_text(self._write(tmpdir, "b.csv", "utf-8-sig")), self.TEXT)

    def test_a_big5_csv_parses_into_rows(self):
        from report_workflow.parsers.structured_parser import parse_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            rows = parse_csv(str(self._write(tmpdir, "big5.csv", "big5")))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["流量 (L/min)"], "2")
            self.assertEqual(rows[1]["實測有效度"], "0.411")

    def test_code_with_big5_comments_is_not_mangled(self):
        """`errors="replace"` did not fail — it succeeded with rubbish.

        A Big5 source came back as U+FFFD with success=True, so mangled
        comments entered the evidence ledger and could be cited in a report.
        That is worse than the CSV case, which at least refused.
        """
        from report_workflow.parsers.code_parser import parse_code

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sensor.py"
            path.write_bytes(
                '# 熱電偶讀取\ndef read_temp(pin):\n    """讀取溫度值。"""\n    return pin\n'
                .encode("big5")
            )
            parsed = parse_code(str(path))
            joined = " ".join(b.get("content") or "" for b in parsed.get("blocks") or [])
            self.assertNotIn("�", joined)
            self.assertIn("讀取溫度值", joined)

    def test_undecodable_code_is_refused_not_mangled(self):
        from report_workflow.parsers.code_parser import parse_code

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "blob.py"
            path.write_bytes(b"\xff\xfe\x00\x00\xff\xff")
            parsed = parse_code(str(path))
            self.assertFalse(parsed.get("success"))
            self.assertIn("UTF-8", parsed.get("error") or "")

    def test_undecodable_bytes_are_refused_not_mangled(self):
        """No latin-1 catch-all: silent mojibake is worse than a refusal."""
        from report_workflow.parsers.source_text import read_source_text

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "binary.csv"
            path.write_bytes(b"\xff\xfe\x00\x00\xff\xff")
            with self.assertRaises(ValueError) as ctx:
                read_source_text(path)
            self.assertIn("UTF-8", str(ctx.exception))


class DerivedStatsContainerTests(unittest.TestCase):
    """The same table analysed the same way whichever file it arrived in.

    Derived statistics were gated on file_type, which stood in for "this
    source has measurement rows". The loop tests that directly, so the proxy
    only meant one thing in practice: a table saved as CSV produced a slope
    and an R², and the identical table pasted into Word produced nothing —
    the quantitative analysis a report is graded on depended on the
    container the author happened to use.
    """

    GRID = [["Flow Rate (L/min)", "Measured Effectiveness (%)"],
            ["2.0", "72.4"], ["3.0", "76.1"], ["4.0", "79.3"], ["5.0", "81.0"]]

    def _derived(self, entry):
        from report_workflow.nodes.evidence_normalize import _derived_stats_units

        return _derived_stats_units([entry], "2026-07-27T00:00:00Z")

    def _csv_entry(self):
        rows = [
            {"block_id": f"b{i}", "block_type": "csv_row",
             "content": json.dumps(dict(zip(self.GRID[0], row)))}
            for i, row in enumerate(self.GRID[1:])
        ]
        return {"file_type": "csv", "file_name": "perf.csv", "parsed_content": rows}

    def _docx_entry(self):
        return {"file_type": "docx", "file_name": "perf.docx", "parsed_content": [
            {"block_id": "table_0", "block_type": "table",
             "content": "whole grid as text", "table_data": self.GRID},
        ]}

    def test_a_word_table_is_analysed_like_a_csv(self):
        from_csv = self._derived(self._csv_entry())
        from_docx = self._derived(self._docx_entry())
        self.assertTrue(from_csv)
        self.assertEqual(len(from_docx), len(from_csv))
        # Same numbers, not merely "some output": only the file name differs.
        self.assertEqual(
            from_docx[0]["content"].replace("perf.docx", "X"),
            from_csv[0]["content"].replace("perf.csv", "X"),
        )

    def test_prose_alone_derives_nothing(self):
        entry = {"file_type": "docx", "file_name": "notes.docx", "parsed_content": [
            {"block_id": "p0", "block_type": "paragraph",
             "content": "Effectiveness rose with flow rate across the run."},
        ]}
        self.assertEqual(self._derived(entry), [])

    def test_a_table_with_one_data_row_derives_nothing(self):
        entry = {"file_type": "docx", "file_name": "thin.docx", "parsed_content": [
            {"block_id": "table_0", "block_type": "table", "content": "grid",
             "table_data": [self.GRID[0], self.GRID[1]]},
        ]}
        self.assertEqual(self._derived(entry), [])


class EmbeddedTableGranularityTests(unittest.TestCase):
    """A table in a DOCX arrived as one evidence entry for the whole grid.

    Six rows of measurements became a single pipe-delimited blob: no row
    could be cited on its own, and the numeric check found no numbers in it
    at all, so honest claims about figures the table plainly held came back
    blocked — the same defect already fixed for CSV rows, in the branch next
    door. The rows were parsed and carried in table_data; nothing read them.
    """

    BLOCK = {
        "block_id": "table_0",
        "block_type": "table",
        "content": "Trial | Effectiveness (%)\n1 | 72.4\n6 | 83.1",
        "table_data": [["Trial", "Outlet Temp (°C)", "Effectiveness (%)"],
                       ["1", "41.2", "72.4"],
                       ["6", "48.6", "83.1"]],
    }

    def test_a_table_becomes_one_block_per_row(self):
        from report_workflow.nodes.evidence_normalize import _table_row_blocks

        rows = _table_row_blocks(self.BLOCK)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["block_type"], "table_row")
        self.assertEqual(
            json.loads(rows[1]["content"])["Effectiveness (%)"], "83.1")

    def test_prose_blocks_are_left_alone(self):
        from report_workflow.nodes.evidence_normalize import _table_row_blocks

        self.assertIsNone(_table_row_blocks(
            {"block_type": "paragraph", "content": "Flow was raised stepwise."}))

    def test_a_header_only_table_stays_whole(self):
        from report_workflow.nodes.evidence_normalize import _table_row_blocks

        self.assertIsNone(_table_row_blocks(
            {"block_type": "table", "content": "h",
             "table_data": [["Trial", "Effectiveness (%)"]]}))

    def test_a_row_grounds_a_claim_about_its_own_figures(self):
        from report_workflow.nodes.evidence_normalize import _table_row_blocks
        from report_workflow.nodes.factuality_check import _check_content_overlap

        row = {"content": _table_row_blocks(self.BLOCK)[1]["content"]}
        # Degrees matter here: the column header writes "(°C)" and the claim
        # writes "°C", and a chart-oriented normalizer folds that to "degc".
        self.assertEqual(
            _check_content_overlap(
                {"claim_text": "Outlet temperature reached 48.6 °C in trial 6."}, row),
            [])
        self.assertEqual(
            _check_content_overlap(
                {"claim_text": "Effectiveness reached 83.1% at the highest flow rate."},
                row),
            [])

    def test_a_fabricated_figure_is_still_rejected(self):
        from report_workflow.nodes.evidence_normalize import _table_row_blocks
        from report_workflow.nodes.factuality_check import _check_content_overlap

        row = {"content": _table_row_blocks(self.BLOCK)[1]["content"]}
        self.assertTrue(_check_content_overlap(
            {"claim_text": "Effectiveness reached 91.5% at the highest flow rate."},
            row))

    def test_an_unrelated_claim_is_still_rejected(self):
        from report_workflow.nodes.evidence_normalize import _table_row_blocks
        from report_workflow.nodes.factuality_check import _check_content_overlap

        row = {"content": _table_row_blocks(self.BLOCK)[1]["content"]}
        self.assertTrue(_check_content_overlap(
            {"claim_text": "The catalyst degraded after 200 cycles of operation."},
            row))


class MultiEvidenceClaimTests(unittest.TestCase):
    """Citing two sources means the claim rests on their union.

    FE demanded that every cited entry satisfy every check, so the most
    ordinary citation pattern in a lab report — the measurement row plus the
    method paragraph that produced it — was blocked twice over: the row
    carries no prose for the term check, the paragraph no number for the
    numeric check. Each was failed by the entry that could not possibly
    satisfy it.
    """

    ROW = {"evidence_id": "E_row",
           "content": '{"Trial": "1", "Efficiency (%)": "88.4"}'}
    METHOD = {"evidence_id": "E_method",
              "content": "Efficiency was measured with the calorimetric "
                         "protocol described in section 3."}

    def _status(self, claim_text, evidence_ids):
        from report_workflow.nodes.factuality_check import run_factuality_check_fe

        matrix = {"claims": [{"claim_id": "C1", "claim_text": claim_text,
                              "evidence_ids": evidence_ids}]}
        result = run_factuality_check_fe(
            [{"claim_id": "C1", "status": "verified"}], matrix,
            [self.ROW, self.METHOD],
        )
        return result[0]["status"]

    def test_measurement_plus_method_is_grounded(self):
        self.assertEqual(
            self._status("Efficiency reached 88.4% under the calorimetric protocol.",
                         ["E_row", "E_method"]),
            "verified",
        )

    def test_padding_citations_does_not_launder_a_fabricated_number(self):
        """An entry with no matching number can never satisfy the number
        check, so citing more sources cannot buy a claim past it."""
        self.assertEqual(
            self._status("Efficiency reached 92.7% under the calorimetric protocol.",
                         ["E_row", "E_method"]),
            "blocked",
        )

    def test_a_single_citation_behaves_exactly_as_before(self):
        self.assertEqual(
            self._status("Efficiency reached 92.7% in trial 1.", ["E_row"]),
            "blocked",
        )


class RowEvidenceNumberTests(unittest.TestCase):
    """A CSV row keeps its units in the header and its numbers in the cells.

    The claim/evidence numeric check needed the unit written beside the
    number, so a row of measurements yielded no numbers at all: an honest
    claim citing the exact row was blocked as ungrounded, with the reason
    "evidence has: (none)" while the row plainly held the figure. Worse, the
    honest claim and a fabricated one were rejected in identical words — for
    row evidence the check could not tell them apart.
    """

    ROW = {
        "content": '{"Trial": "1", "Voltage (V)": "12.1", '
                   '"Leakage (mA)": "<0.01", "Efficiency (%)": "88.4"}'
    }

    def _reasons(self, text):
        from report_workflow.nodes.factuality_check import _check_content_overlap

        return _check_content_overlap({"claim_text": text}, self.ROW)

    def test_a_value_in_the_row_grounds_the_claim(self):
        self.assertEqual(self._reasons("Efficiency reached 88.4% in trial 1."), [])
        self.assertEqual(self._reasons("The measured voltage was 12.1 V."), [])

    def test_a_fabricated_value_is_still_rejected(self):
        reasons = self._reasons("Efficiency reached 92.7% in trial 1.")
        self.assertTrue(reasons)
        # The diagnosis must name what the row actually holds, not "(none)".
        self.assertIn("88.4", reasons[0])

    def test_a_detection_limit_is_not_a_reading(self):
        """"<0.01" bounds the leakage; it does not measure it."""
        reasons = self._reasons("Leakage current was 0.01 mA in trial 1.")
        self.assertTrue(reasons)
        self.assertIn("bound", reasons[0])

    def test_precision_inflation_is_caught_in_rows_too(self):
        reasons = self._reasons("Efficiency reached 88.42% in trial 1.")
        self.assertTrue(reasons)
        self.assertIn("precision", reasons[0])


class UnfilledTableTests(unittest.TestCase):
    """A table exported before anyone filled it in is not measurements.

    Spreadsheet exports routinely carry trailing ",,," rows, and a table
    prepared for an experiment that has not run yet is all dashes. Both used
    to become evidence entries — and the QA gate's "at least 5 evidence
    entries" counts entries, so three blank rows under two real readings
    cleared a bar that two readings should not clear. The dashes were also
    typed quantitative, because "%" appears in the column name.
    """

    def _blocks(self, text):
        import os

        from report_workflow.parsers.structured_parser import parse_structured

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "export.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            return parse_structured(path, "csv")["blocks"]

    def test_trailing_blank_rows_are_not_evidence(self):
        blocks = self._blocks(
            "Trial,Voltage (V),Efficiency (%)\n1,12.1,88.4\n2,12.3,89.1\n,,\n,,\n,,\n"
        )
        self.assertEqual(len(blocks), 2)

    def test_a_zero_reading_is_a_measurement_not_a_blank(self):
        blocks = self._blocks("Trial,Leakage (mA)\n1,0\n2,0.0\n")
        self.assertEqual(len(blocks), 2)

    def test_placeholder_row_is_not_quantitative(self):
        from report_workflow.nodes.evidence_normalize import determine_evidence_type

        row = '{"Trial": "1", "Voltage (V)": "—", "Efficiency (%)": "N/A"}'
        self.assertEqual(determine_evidence_type(row, "table_row"), "qualitative")

    def test_a_filled_row_is_still_quantitative(self):
        from report_workflow.nodes.evidence_normalize import determine_evidence_type

        row = '{"Trial": "1", "Voltage (V)": "12.1", "Efficiency (%)": "88.4"}'
        self.assertEqual(determine_evidence_type(row, "table_row"), "quantitative")


class DegenerateSourceDiagnosisTests(unittest.TestCase):
    """A parse failure must describe the file, not this build.

    An empty file and a corrupt one both came back with the fallback parser
    announcing it "is not implemented in the local MVP; deterministic parser
    could not handle file_type='md'" — telling a student who attached a
    zero-byte file that Markdown is unsupported. The specific diagnosis was
    already computed and then discarded.
    """

    def _error(self, name, content):
        from report_workflow.nodes.source_parse import parse_single_source

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / name
            path.write_text(content, encoding="utf-8")
            parsed = parse_single_source({
                "file_name": name, "file_path": str(path),
                "file_type": name.rsplit(".", 1)[-1], "artifact_role": "source_data",
            })
            return parsed.get("error") or ""

    def test_an_empty_file_is_reported_as_empty(self):
        error = self._error("empty.md", "")
        self.assertIn("no readable content", error)
        self.assertNotIn("local MVP", error)

    def test_a_corrupt_document_reports_the_parser_diagnosis(self):
        error = self._error("broken.docx", "not really a word file")
        self.assertNotIn("local MVP", error)
        self.assertTrue(error.strip(), "expected a diagnosis")

    def test_a_readable_file_still_parses(self):
        from report_workflow.nodes.source_parse import parse_single_source

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "notes.md"
            path.write_text("# Notes\n\nA sentence with enough content to parse.\n",
                            encoding="utf-8")
            parsed = parse_single_source({
                "file_name": "notes.md", "file_path": str(path),
                "file_type": "md", "artifact_role": "source_data",
            })
            self.assertTrue(parsed.get("blocks"))


class EvidencePolicyReportingTests(unittest.TestCase):
    """All three evidence-policy checks report the same way.

    Two of them wrote only to the logger, so `evidence_policy_warnings` read
    empty on a run that had visibly warned twice, and every message named
    `academic_paper` whichever profile was actually running.
    """

    def _reasons_and_warnings(self, profile, roles, count=12):
        from report_workflow.nodes.qa_gate import _source_diversity_reasons

        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = profile
        entries = [
            {"evidence_id": f"e{i}", "source_role": roles[i % len(roles)]}
            for i in range(count)
        ]
        state.plan["claim_matrix"] = {"claims": []}
        with patch("report_workflow.nodes.qa_gate._load_jsonl", return_value=entries):
            reasons = _source_diversity_reasons(state)
        return reasons, state.qa.get("evidence_policy_warnings", [])

    def test_all_three_checks_reach_the_structured_report(self):
        _reasons, warnings = self._reasons_and_warnings(
            "engineering_lab_report", ["primary_source"]
        )
        joined = " | ".join(warnings)
        self.assertIn("graph_analysis", joined)
        self.assertIn("code_artifact", joined)
        self.assertIn("research_document", joined)

    def test_no_warning_names_a_profile_that_is_not_running(self):
        _reasons, warnings = self._reasons_and_warnings(
            "engineering_lab_report", ["primary_source"]
        )
        self.assertTrue(warnings, "expected evidence-policy warnings")
        for warning in warnings:
            self.assertNotIn("academic_paper", warning)

    def test_hard_reason_names_the_running_profile(self):
        reasons, _warnings = self._reasons_and_warnings(
            "engineering_lab_report", ["primary_source"], count=3
        )
        shortfall = [r for r in reasons if "5 evidence entries" in r]
        self.assertTrue(shortfall, f"expected an evidence-count reason: {reasons}")
        self.assertIn("engineering_lab_report", shortfall[0])
        self.assertNotIn("academic_paper", shortfall[0])


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

    def test_the_same_content_twice_is_one_piece_of_material(self):
        """Attaching a thin file twice used to clear the source-base bar.

        A three-row CSV attached at two paths produced six entries, and this
        check counted entries, so six cleared a bar three rows should not.
        """
        from report_workflow.nodes.qa_gate import _source_diversity_reasons
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        rows = [f'{{"Trial": "{i}", "Voltage (V)": "12.{i}"}}' for i in range(3)]
        doubled = [
            {"evidence_id": f"e{i}", "source_role": "code_artifact", "content": content}
            for i, content in enumerate(rows + rows)
        ]
        state.sources["evidence_ledger_path"] = ""
        state.plan["claim_matrix"] = {"claims": []}
        with patch("report_workflow.nodes.qa_gate._load_jsonl", return_value=doubled):
            reasons = _source_diversity_reasons(state)
        self.assertTrue(any("5 evidence entries" in r for r in reasons))
        self.assertTrue(any("found 3" in r for r in reasons))

    def test_five_genuinely_different_rows_still_clear_the_bar(self):
        from report_workflow.nodes.qa_gate import _source_diversity_reasons
        state = ReportState.new("report", [], "out")
        state.spec["report_profile"] = "academic_paper"
        entries = [
            {"evidence_id": f"e{i}", "source_role": "code_artifact",
             "content": f'{{"Trial": "{i}"}}'}
            for i in range(5)
        ]
        state.sources["evidence_ledger_path"] = ""
        state.plan["claim_matrix"] = {"claims": []}
        with patch("report_workflow.nodes.qa_gate._load_jsonl", return_value=entries):
            reasons = _source_diversity_reasons(state)
        self.assertFalse(any("5 evidence entries" in r for r in reasons))

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
