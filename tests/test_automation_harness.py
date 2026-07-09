import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from report_workflow.agent_wrapper import (  # noqa: E402
    get_controlled_next_action,
    submit_controlled_action,
)
from report_workflow.automation_harness import (  # noqa: E402
    load_or_create_manifest,
    run_controlled_stage,
)
from report_workflow.run_workflow import WorkflowStage, WorkflowStep, prepare_workflow  # noqa: E402
from report_workflow.state import ReportState, run_dir_for  # noqa: E402


def _all_packages_present(_module_name):
    return object()


def _read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _prepare(tmpdir: str, profile: str = "academic_paper") -> ReportState:
    src = Path(tmpdir) / "source.txt"
    src.write_text(
        "The pilot program enrolled 42 participants and reduced processing time by 20 percent.",
        encoding="utf-8",
    )
    with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
        return prepare_workflow(
            f"write a {profile}",
            [str(src)],
            str(Path(tmpdir) / "out"),
            report_profile=profile,
        )


def _prepare_with_chart_recommendation(tmpdir: str) -> ReportState:
    src = Path(tmpdir) / "measurements.csv"
    src.write_text(
        "condition,pressure_kpa\nA,118\nB,82\nC,96\n",
        encoding="utf-8",
    )
    with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
        return prepare_workflow(
            "write a compact report with a source-backed chart",
            [str(src)],
            str(Path(tmpdir) / "out"),
            report_profile="custom",
        )


def _fake_validators() -> dict:
    return {
        "claim_matrix": lambda _job_id, _workspace_root=None: {"status": "ok"},
        "outline": lambda _job_id, _workspace_root=None: {"status": "ok"},
        "drafts": lambda _job_id, _workspace_root=None: {"status": "ok"},
        "revision_plan": lambda _job_id, _workspace_root=None: {"status": "ok"},
        "artifact_lint": lambda _job_id, _workspace_root=None: {"status": "ok"},
        "publish": lambda _job_id, _workspace_root=None: {"status": "completed"},
    }


def _write_claim_matrix(state: ReportState) -> str:
    run_dir = run_dir_for(state)
    evidence_id = _read_jsonl(state.sources["evidence_ledger_path"])[0]["evidence_id"]
    (run_dir / "claim_matrix.json").write_text(json.dumps({
        "claims": [{
            "claim_id": "c1",
            "claim_text": "The pilot program enrolled 42 participants.",
            "claim_type": "statistical",
            "risk_level": "low",
            "status": "supported",
            "evidence_ids": [evidence_id],
            "requires_hedged_wording": False,
            "claim_role": "primary",
        }]
    }), encoding="utf-8")
    return evidence_id


def _write_outline(state: ReportState) -> None:
    run_dir = run_dir_for(state)
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


def _write_drafts(state: ReportState, evidence_id: str) -> None:
    run_dir = run_dir_for(state)
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
            text = (
                f"# {section_id.title()}\n\n"
                f"The pilot program enrolled 42 participants [CITE:{evidence_id}]."
            )
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


class AutomationHarnessTests(unittest.TestCase):
    def test_manifest_initializes_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir)
            workspace_root = state.output["workspace_root"]

            first = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            second = get_controlled_next_action(state.job_id, workspace_root=workspace_root)

            self.assertEqual(first["stage"], "claim_matrix")
            self.assertEqual(second["stage"], "claim_matrix")
            self.assertTrue(Path(first["harness_manifest_path"]).exists())
            self.assertIn("claim_matrix.json", first["allowed_write_paths"][0])

    def test_start_report_task_creates_manifest_before_authoring(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from report_workflow.agent_wrapper import start_report_task

            src = Path(tmpdir) / "source.txt"
            src.write_text("The pilot enrolled 42 participants.", encoding="utf-8")
            # Keep this unit test hermetic: mock both Python-package detection and
            # external-tool (pandoc/mmdc) detection so start readiness does not depend
            # on what happens to be installed on the runner. Real-tool coverage lives
            # in the end-to-end benchmark, not here.
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present), \
                 patch("report_workflow.preflight._find_executable", return_value="/usr/bin/tool"):
                result = start_report_task(
                    "write an academic report",
                    [str(src)],
                    output_dir=str(Path(tmpdir) / "out"),
                    report_profile="academic_paper",
                    preflight_confirmed=True,
                    preflight_decisions={
                        "confirmed_by_user": True,
                        "install_decisions": {},
                        "feature_decisions": {
                            "web_research": "skip",
                            "notebook_sync": "skip",
                        },
                    },
                )

            self.assertEqual(result["status"], "awaiting_agent_artifacts")
            self.assertEqual(result["controlled_next_action"]["stage"], "claim_matrix")
            self.assertTrue(Path(result["harness_manifest_path"]).exists())

    def test_lazy_manifest_rejects_preexisting_future_stage_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
            state.checkpoint("TEST")
            workspace_root = state.output["workspace_root"]
            run_dir = run_dir_for(state)

            (run_dir / "claim_matrix.json").write_text("{}", encoding="utf-8")
            (run_dir / "outline.json").write_text("{}", encoding="utf-8")
            (run_dir / "structured_drafts.json").write_text("{}", encoding="utf-8")
            figure_dir = run_dir / "section_drafts"
            figure_dir.mkdir()
            (figure_dir / "figure_plan.json").write_text('{"figures":[]}', encoding="utf-8")

            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)

            self.assertEqual(result["status"], "scope_violation")
            self.assertEqual(result["stage"], "claim_matrix")
            self.assertEqual(
                {violation["relative_path"] for violation in result["violations"]},
                {"outline.json", "structured_drafts.json", "section_drafts/figure_plan.json"},
            )

    def test_generated_starter_figure_plan_does_not_block_claim_stage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare_with_chart_recommendation(tmpdir)
            workspace_root = state.output["workspace_root"]
            run_dir = run_dir_for(state)
            plan_path = run_dir / "section_drafts" / "figure_plan.json"

            self.assertTrue(plan_path.exists())
            self.assertEqual(state.runtime["auto_figure_plan"]["status"], "generated")

            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(action["stage"], "claim_matrix")

            (run_dir / "claim_matrix.json").write_text("{}", encoding="utf-8")
            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_stage"], "outline")

    def test_revise_existing_adds_revision_plan_stage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("revise report", [], str(Path(tmpdir) / "out"))
            state.spec["task_intent"] = "revise_existing"
            state.checkpoint("TEST")

            _state, _run_dir, manifest = load_or_create_manifest(
                state.job_id,
                workspace_root=state.output["workspace_root"],
            )

            self.assertEqual(
                manifest["stage_order"],
                ["claim_matrix", "outline", "drafts", "revision_plan", "artifact_lint", "publish"],
            )
            self.assertEqual(
                manifest["stages"]["revision_plan"]["validation_tool"],
                "submit_controlled_action",
            )

    def test_stage_run_can_suppress_substep_events_for_dry_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("dry run", [], str(Path(tmpdir) / "out"))
            run_dir = run_dir_for(state)
            stage = WorkflowStage("DRY_RUN_STAGE", (WorkflowStep("NOP", lambda current: current),))

            stage.run(state, emit_events=False)
            self.assertFalse((run_dir / "job_events.jsonl").exists())

            stage.run(state)
            self.assertTrue((run_dir / "job_events.jsonl").exists())

    def test_allowed_write_scope_and_stage_advancement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
            state.checkpoint("TEST")
            workspace_root = state.output["workspace_root"]
            run_dir = run_dir_for(state)

            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(action["stage"], "claim_matrix")
            self.assertEqual([Path(p).name for p in action["allowed_write_paths"]], ["claim_matrix.json"])

            (run_dir / "claim_matrix.json").write_text("{}", encoding="utf-8")
            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_stage"], "outline")

            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(action["stage"], "outline")
            self.assertEqual([Path(p).name for p in action["allowed_write_paths"]], ["outline.json"])

            (run_dir / "outline.json").write_text("{}", encoding="utf-8")
            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)
            self.assertEqual(result["next_stage"], "drafts")

            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(action["stage"], "drafts")
            self.assertIn(str(run_dir / "structured_drafts.json"), action["allowed_write_paths"])
            self.assertIn(str(run_dir / "sentence_map.jsonl"), action["allowed_write_paths"])

            (run_dir / "structured_drafts.json").write_text("{}", encoding="utf-8")
            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)
            self.assertEqual(result["next_stage"], "artifact_lint")

            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(action["stage"], "artifact_lint")
            self.assertEqual(action["allowed_write_paths"], [])

            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)
            self.assertEqual(result["status"], "ready_to_publish")
            self.assertEqual(result["next_stage"], "publish")

            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(action["stage"], "publish")
            self.assertEqual(action["allowed_write_paths"], [])

    def test_scope_violation_blocks_passed_artifact_drift(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
            state.checkpoint("TEST")
            workspace_root = state.output["workspace_root"]
            run_dir = run_dir_for(state)

            (run_dir / "claim_matrix.json").write_text('{"claims":[]}', encoding="utf-8")
            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)
            self.assertEqual(result["next_stage"], "outline")

            (run_dir / "claim_matrix.json").write_text('{"claims":[{"claim_id":"changed"}]}', encoding="utf-8")
            result = run_controlled_stage(state.job_id, _fake_validators(), workspace_root=workspace_root)

            self.assertEqual(result["status"], "scope_violation")
            self.assertEqual(result["stage"], "outline")
            self.assertEqual(result["violations"][0]["relative_path"], "claim_matrix.json")

    def test_validation_failure_stays_on_minimal_stage_with_repair_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
            state.checkpoint("TEST")
            workspace_root = state.output["workspace_root"]
            validators = {
                **_fake_validators(),
                "claim_matrix": lambda _job_id, _workspace_root=None: {
                    "status": "validation_failed",
                    "message": "claim_matrix.json is malformed",
                    "error_details": "bad claims",
                },
            }

            result = run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)

            self.assertEqual(result["status"], "validation_failed")
            self.assertEqual(result["next_stage"], "claim_matrix")
            self.assertEqual(action["stage"], "claim_matrix")
            self.assertEqual(action["status"], "failed")
            self.assertIn("bad claims", json.dumps(action["repair_context"]))

    def test_artifact_lint_failure_routes_to_repair_stage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
            state.checkpoint("TEST")
            workspace_root = state.output["workspace_root"]
            validators = {
                **_fake_validators(),
                "artifact_lint": lambda _job_id, _workspace_root=None: {
                    "status": "issues_found",
                    "issues": [{
                        "severity": "error",
                        "artifact": "outline.json",
                        "json_path": "$.sections",
                        "message": "missing section",
                    }],
                },
            }

            run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            result = run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)

            self.assertEqual(result["status"], "validation_failed")
            self.assertEqual(result["next_stage"], "outline")
            self.assertEqual(action["stage"], "outline")
            self.assertEqual(action["status"], "failed")

    def test_unroutable_read_only_stage_failure_returns_blocked_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = ReportState.new("controlled report", [], str(Path(tmpdir) / "out"))
            state.checkpoint("TEST")
            workspace_root = state.output["workspace_root"]
            run_dir = run_dir_for(state)
            validators = {
                **_fake_validators(),
                "publish": lambda _job_id, _workspace_root=None: {
                    "status": "validation_failed",
                    "message": "QA_GATE failed for an environment-only condition",
                    "error_details": "unmapped failure",
                },
            }

            (run_dir / "claim_matrix.json").write_text("{}", encoding="utf-8")
            run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            (run_dir / "outline.json").write_text("{}", encoding="utf-8")
            run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            (run_dir / "structured_drafts.json").write_text("{}", encoding="utf-8")
            run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)

            result = run_controlled_stage(state.job_id, validators, workspace_root=workspace_root)
            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)

            self.assertEqual(result["status"], "blocked_non_author_repair")
            self.assertEqual(result["stage"], "publish")
            self.assertEqual(result["allowed_repair_paths"], [])
            self.assertEqual(action["status"], "blocked_non_author_repair")
            self.assertIn("unmapped failure", json.dumps(action["repair_context"]))

    def test_section_task_does_not_instruct_controlled_agent_to_write_project_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir)
            run_dir = run_dir_for(state)
            section_task = (run_dir / "agent_tasks" / "03_section_draft.md").read_text(encoding="utf-8")
            normalized = " ".join(section_task.split())

            self.assertIn("Do not write `project_identity.json` during controlled authoring", normalized)
            self.assertNotIn("write a confirmed `project_identity.json`", normalized)

    def test_minimal_new_draft_controlled_flow_reaches_publish_stage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _prepare(tmpdir)
            workspace_root = state.output["workspace_root"]

            action = get_controlled_next_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(action["stage"], "claim_matrix")

            evidence_id = _write_claim_matrix(state)
            result = submit_controlled_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_stage"], "outline")

            _write_outline(state)
            result = submit_controlled_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_stage"], "drafts")

            _write_drafts(state, evidence_id)
            result = submit_controlled_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_stage"], "artifact_lint")

            result = submit_controlled_action(state.job_id, workspace_root=workspace_root)
            self.assertEqual(result["status"], "ready_to_publish")
            self.assertEqual(result["next_stage"], "publish")

            with patch("report_workflow.agent_wrapper.submit_and_publish_report", return_value={
                "status": "completed",
                "job_id": state.job_id,
                "final_docx_path": str(run_dir_for(state) / "final.docx"),
            }):
                result = submit_controlled_action(state.job_id, workspace_root=workspace_root)

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["next_stage"], "completed")


if __name__ == "__main__":
    unittest.main()
