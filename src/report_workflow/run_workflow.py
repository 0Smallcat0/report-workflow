"""Main workflow orchestrator."""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from .state import ReportState, run_dir_for
from .errors import AgentWorkRequired, QAHardBlockError
from .runtime_support import append_job_event
from .preflight import run_preflight_checks
from .nodes.remediation_router import write_remediation_plan
from .nodes.intake import run_intake
from .nodes.guideline_select import run_guideline_select
from .nodes.blueprint_plan import run_blueprint_plan
from .nodes.corpus_build import run_corpus_build
from .nodes.source_parse import run_source_parse
from .nodes.evidence_normalize import run_evidence_normalize
from .nodes.evidence_store import run_evidence_store
from .nodes.figure_recommend import run_figure_recommend
from .nodes.figure_plan_audit import run_figure_plan_audit
from .nodes.notebook_sync import run_notebook_sync
from .nodes.agent_tasks import run_agent_task_briefs
from .nodes.claim_plan import run_claim_plan
from .nodes.outline_plan import run_outline_plan
from .nodes.section_draft import run_section_draft
from .nodes.paper_scope_freeze import run_paper_scope_freeze
from .nodes.section_plan_freeze import run_section_plan_freeze
from .nodes.front_matter_build import run_front_matter_build
from .nodes.abstract_check import run_abstract_check
from .nodes.figure_build import run_figure_build
from .nodes.figure_quality import run_figure_quality
from .nodes.methods_protocol_build import run_methods_protocol_build
from .nodes.revision_apply import run_revision_apply
from .nodes.merge_draft import run_merge_draft
from .nodes.project_identity_gate import run_project_identity_gate
from .nodes.admissions_tone_gate import run_admissions_tone_gate
from .nodes.section_role_check import run_section_role_check
from .nodes.citation_bind import run_citation_bind
from .nodes.reference_verify import run_reference_verify
from .nodes.factuality_check import run_factuality_check
from .nodes.research_execute import run_research_execute
from .nodes.claim_verify_execute import run_claim_verify_execute
from .nodes.base_document_parse import run_base_document_parse
from .nodes.qa_gate import run_qa_gate
from .nodes.scholarly_quality import run_scholarly_quality
from .nodes.style_pass import run_style_pass
from .nodes.publication_naturalness_pass import run_publication_naturalness_pass
from .nodes.admissions_monograph_polish import run_admissions_monograph_polish
from .nodes.heading_contract_check import run_heading_contract_check
from .nodes.source_appendix_render import run_source_appendix_render
from .nodes.docx_render import run_docx_render
from .nodes.post_render_repair import run_post_render_repair
from .nodes.post_render_validate import run_post_render_validate
from .nodes.visual_render_check import run_visual_render_check
from .nodes.reference_reality_check import run_reference_reality_check
from .nodes.reference_relevance_gate import run_reference_relevance_gate
from .nodes.final_publish import run_final_publish
from .nodes.supplementary_package_build import run_supplementary_package_build
from .nodes.artifacts import run_artifacts


NodeFn = Callable[[ReportState], ReportState]


@dataclass(frozen=True)
class WorkflowStep:
    """Internal workflow substep.

    Steps preserve diagnostic precision without expanding the public DAG.
    """

    name: str
    run: NodeFn


@dataclass(frozen=True)
class WorkflowStage:
    """Public workflow stage checkpointed by the runner."""

    name: str
    steps: tuple[WorkflowStep, ...]

    def run(self, state: ReportState, *, emit_events: bool = True) -> ReportState:
        for step in self.steps:
            step_name = f"{self.name}/{step.name}"
            if emit_events:
                append_job_event(state, step_name, "start", "running")
            try:
                state = step.run(state)
                if emit_events:
                    append_job_event(state, step_name, "success", state.status)
            except AgentWorkRequired as exc:
                if emit_events:
                    append_job_event(
                        state,
                        step_name,
                        "agent_work_required",
                        "awaiting_agent_artifacts",
                        {"missing_artifacts": exc.missing_artifacts},
                    )
                raise AgentWorkRequired(
                    f"{step_name}: {exc}",
                    exc.missing_artifacts,
                ) from exc
            except QAHardBlockError as exc:
                if emit_events:
                    append_job_event(state, step_name, "failure", "failed", {"error": str(exc)})
                raise QAHardBlockError(f"{step_name}: {exc}", hint=getattr(exc, "hint", "")) from exc
            except Exception as exc:
                if emit_events:
                    append_job_event(
                        state,
                        step_name,
                        "failure",
                        "failed",
                        {"error": f"{type(exc).__name__}: {exc}"},
                    )
                raise RuntimeError(f"{step_name}: {type(exc).__name__}: {exc}") from exc
        return state

    def as_node(self) -> tuple[str, NodeFn]:
        return self.name, self.run


def _step(name: str, run: NodeFn) -> WorkflowStep:
    return WorkflowStep(name, run)


def _stage(name: str, *steps: WorkflowStep) -> WorkflowStage:
    return WorkflowStage(name, tuple(steps))


def workflow_nodes() -> list[tuple[str, object]]:
    """Return the ordered public workflow stage list."""
    return prepare_nodes() + validate_nodes() + render_nodes()


def prepare_nodes() -> list[tuple[str, object]]:
    """Return stages that prepare deterministic source/evidence artifacts."""
    return [stage.as_node() for stage in prepare_stages()]


def prepare_stages() -> list[WorkflowStage]:
    return [
        _stage(
            "SPEC_PLAN",
            _step("INTAKE", run_intake),
            _step("GUIDELINE_SELECT", run_guideline_select),
            _step("BLUEPRINT_PLAN", run_blueprint_plan),
        ),
        _stage(
            "SOURCE_INGEST",
            _step("CORPUS_BUILD", run_corpus_build),
            _step("SOURCE_PARSE", run_source_parse),
            _step("BASE_DOCUMENT_PARSE", run_base_document_parse),
        ),
        _stage(
            "EVIDENCE_BUILD",
            _step("EVIDENCE_NORMALIZE", run_evidence_normalize),
            _step("EVIDENCE_STORE", run_evidence_store),
        ),
        _stage("FIGURE_RECOMMEND", _step("FIGURE_RECOMMEND", run_figure_recommend)),
        _stage("NOTEBOOK_SYNC", _step("NOTEBOOK_SYNC", run_notebook_sync)),
        _stage("AGENT_TASKS", _step("AGENT_TASKS", run_agent_task_briefs)),
    ]


def validate_nodes() -> list[tuple[str, object]]:
    """Return stages that validate external agent-produced artifacts."""
    return [stage.as_node() for stage in validate_stages()]


def validate_stages() -> list[WorkflowStage]:
    return [
        _stage(
            "AGENT_ARTIFACTS",
            _step("CLAIM_PLAN", run_claim_plan),
            _step("OUTLINE_PLAN", run_outline_plan),
            _step("SECTION_DRAFT", run_section_draft),
        ),
        _stage(
            "PLAN_LOCK",
            _step("PAPER_SCOPE_FREEZE", run_paper_scope_freeze),
            _step("SECTION_PLAN_FREEZE", run_section_plan_freeze),
        ),
        _stage(
            "METADATA_GATE",
            _step("FRONT_MATTER_BUILD", run_front_matter_build),
            _step("ABSTRACT_CHECK", run_abstract_check),
        ),
        _stage(
            "CONTENT_ASSEMBLY",
            _step("METHODS_PROTOCOL_BUILD", run_methods_protocol_build),
            _step("FIGURE_PLAN_AUDIT", run_figure_plan_audit),
            _step("FIGURE_BUILD", run_figure_build),
            _step("REVISION_APPLY", run_revision_apply),
            _step("MERGE_DRAFT", run_merge_draft),
        ),
        _stage(
            "DRAFT_GATES",
            _step("PROJECT_IDENTITY_GATE", run_project_identity_gate),
            _step("ADMISSIONS_TONE_GATE", run_admissions_tone_gate),
            _step("SECTION_ROLE_CHECK", run_section_role_check),
        ),
        _stage(
            "EVIDENCE_AND_CLAIMS",
            _step("CITATION_BIND", run_citation_bind),
            _step("REFERENCE_VERIFY", run_reference_verify),
            _step("FACTUALITY_CHECK", run_factuality_check),
            _step("RESEARCH_EXECUTE", run_research_execute),
            _step("CLAIM_VERIFY_EXECUTE", run_claim_verify_execute),
        ),
        _stage(
            "FINAL_QA",
            _step("FIGURE_QUALITY", run_figure_quality),
            _step("SCHOLARLY_QUALITY", run_scholarly_quality),
            _step("QA_GATE", run_qa_gate),
        ),
    ]


def render_nodes() -> list[tuple[str, object]]:
    """Return stages that render and package a validated workflow."""
    return [stage.as_node() for stage in render_stages()]


def render_stages() -> list[WorkflowStage]:
    return [
        _stage(
            "TEXT_POLISH",
            _step("STYLE_PASS", run_style_pass),
            _step("PUBLICATION_NATURALNESS_PASS", run_publication_naturalness_pass),
            _step("ADMISSIONS_MONOGRAPH_POLISH", run_admissions_monograph_polish),
            _step("HEADING_CONTRACT_CHECK", run_heading_contract_check),
        ),
        _stage(
            "DOCX_BUILD",
            _step("DOCX_RENDER", run_docx_render),
            _step("POST_RENDER_REPAIR", run_post_render_repair),
        ),
        _stage(
            "RENDER_QA",
            _step("POST_RENDER_VALIDATE", run_post_render_validate),
            _step("VISUAL_RENDER_CHECK", run_visual_render_check),
        ),
        _stage(
            "REFERENCE_QA",
            _step("REFERENCE_REALITY_CHECK", run_reference_reality_check),
            _step("REFERENCE_RELEVANCE_GATE", run_reference_relevance_gate),
        ),
        _stage(
            "PUBLISH",
            _step("SOURCE_APPENDIX_RENDER", run_source_appendix_render),
            _step("FINAL_PUBLISH", run_final_publish),
            _step("SUPPLEMENTARY_PACKAGE_BUILD", run_supplementary_package_build),
            _step("ARTIFACTS", run_artifacts),
        ),
    ]


def _start_index_for_resume(state: ReportState, nodes: list[tuple[str, object]]) -> int:
    current = state.runtime.get("current_node")
    if state.status == "completed":
        return len(nodes)
    if not current:
        return 0
    names = [name for name, _ in nodes]
    if current == "FAILED":
        raise QAHardBlockError("Cannot resume a failed workflow without remediation")
    try:
        return names.index(current)
    except ValueError:
        legacy_stage = _stage_name_for_legacy_node(current)
        if legacy_stage in names:
            return names.index(legacy_stage)
        return 0


def _stage_name_for_legacy_node(node_name: str) -> str | None:
    stage_aliases = {
        "AGENT_ARTIFACT_INTAKE": "AGENT_ARTIFACTS",
        "PLAN_FREEZE": "PLAN_LOCK",
        "DOC_METADATA_GATE": "METADATA_GATE",
        "DRAFT_ASSEMBLY": "CONTENT_ASSEMBLY",
        "CITATION_LAYER": "EVIDENCE_AND_CLAIMS",
    }
    if node_name in stage_aliases:
        return stage_aliases[node_name]
    for stage in prepare_stages() + validate_stages() + render_stages():
        if any(step.name == node_name for step in stage.steps):
            return stage.name
    return None


def _run_nodes(state: ReportState, nodes: list[tuple[str, object]]) -> ReportState:
    for node_name, node_fn in nodes:
        state.checkpoint(node_name)
        append_job_event(state, node_name, "start", "running")
        try:
            state = node_fn(state)
            append_job_event(state, node_name, "success", state.status)
        except AgentWorkRequired as e:
            print(f"[WORKFLOW] Node {node_name!r} requires agent artifacts: {e}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {e}"
            state.runtime["required_agent_artifacts"] = e.missing_artifacts
            state.status = "awaiting_agent_artifacts"
            append_job_event(state, node_name, "agent_work_required", state.status, {"missing_artifacts": e.missing_artifacts})
            state.checkpoint("AWAITING_AGENT_ARTIFACTS")
            raise
        except QAHardBlockError as e:
            print(f"[WORKFLOW] Node {node_name!r} raised QAHardBlockError: {e}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {e}"
            state.status = "failed"
            try:
                write_remediation_plan(state, [str(e)])
            except Exception as rem_err:
                # Log but don't silently swallow - remediation failure is a secondary issue
                print(f"[WORKFLOW] WARNING: Failed to write remediation plan: {rem_err}", file=sys.stderr)
            append_job_event(state, node_name, "failure", "failed", {"error": str(e)})
            state.checkpoint("FAILED")
            raise
        except Exception as e:
            print(f"[WORKFLOW] Node {node_name!r} failed with {type(e).__name__}: {e}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {type(e).__name__}: {e}"
            state.status = "failed"
            append_job_event(state, node_name, "failure", "failed", {"error": f"{type(e).__name__}: {e}"})
            state.checkpoint("FAILED")
            raise
    return state
def prepare_workflow(
    user_prompt: str,
    uploaded_files: list[str],
    output_dir: str | None,
    *,
    report_profile: str | None = None,
    intent: str = "new_draft",
    artifact_role_map: dict[str, str] | None = None,
    front_matter: dict | None = None,
    project_identity: dict | None = None,
    enable_research: bool = False,
    enable_notebook_sync: bool = False,
    notebooklm_notebook_id: str | None = None,
    notebooklm_storage_path: str | None = None,
    reference_docx: str | None = None,
) -> ReportState:
    """Prepare deterministic artifacts and agent task briefs.

    Args:
        intent: 'new_draft' or 'revise_existing'.
        artifact_role_map: mapping from file name to artifact role
            ('source_data' or 'base_document').
    """
    state = ReportState.new(user_prompt, uploaded_files, output_dir, front_matter=front_matter)
    if report_profile:
        state.spec["report_profile_override"] = report_profile
    state.spec["task_intent"] = intent
    if artifact_role_map:
        state.spec["artifact_role_map"] = artifact_role_map
    if front_matter:
        state.spec["front_matter"] = front_matter
    if project_identity:
        state.spec["project_identity"] = project_identity
        identity_path = run_dir_for(state) / "project_identity.json"
        identity_path.write_text(json.dumps(project_identity, indent=2), encoding="utf-8")
    if enable_research:
        state.flags["enable_research"] = True
    if enable_notebook_sync:
        state.flags["enable_notebook_sync"] = True
    if notebooklm_notebook_id:
        state.spec["notebooklm_notebook_id"] = notebooklm_notebook_id
    if notebooklm_storage_path:
        state.spec["notebooklm_storage_path"] = notebooklm_storage_path
    if reference_docx:
        state.spec["reference_docx_path"] = str(Path(reference_docx).resolve())
    try:
        state = run_preflight_checks(state)
    except QAHardBlockError as e:
        state.runtime["error"] = f"PREFLIGHT: {e}"
        state.status = "failed"
        try:
            write_remediation_plan(state, [str(e)])
        except Exception as rem_err:
            print(f"[WORKFLOW] WARNING: Failed to write remediation plan: {rem_err}", file=sys.stderr)
        append_job_event(state, "PREFLIGHT", "failure", "failed", {"error": str(e)})
        state.checkpoint("PREFLIGHT_FAILED")
        raise
    state = _run_nodes(state, prepare_nodes())
    state.checkpoint("AWAITING_AGENT_ARTIFACTS")
    return state


def _load_json_for_gate(path: str | None, label: str) -> dict:
    if not path:
        raise QAHardBlockError(f"Cannot render before validate writes {label}")
    p = Path(path)
    if not p.exists():
        raise QAHardBlockError(f"Cannot render because {label} is missing: {path}")
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise QAHardBlockError(f"Cannot render because {label} is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise QAHardBlockError(f"Cannot render because {label} is malformed")
    return data


def _assert_render_ready(state: ReportState) -> None:
    """Require evidence that the normal QA gate actually passed before render."""
    if state.flags.get("bypass_qa_gate"):
        raise QAHardBlockError("Cannot render with bypass_qa_gate enabled")
    if state.status != "validated":
        raise QAHardBlockError(
            f"Cannot render before validate completes; current status is {state.status!r}"
        )
    if state.qa.get("qa_decision") != "pass":
        raise QAHardBlockError("Cannot render before validate produces qa_decision=pass")

    qa_summary = _load_json_for_gate(state.qa.get("qa_summary_path"), "qa_summary.json")
    if qa_summary.get("qa_decision") != "pass":
        raise QAHardBlockError("Cannot render because qa_summary.json does not record qa_decision=pass")
    if qa_summary.get("artifact_completeness_status") != "pass":
        raise QAHardBlockError("Cannot render because artifact completeness did not pass")
    if qa_summary.get("hard_fail_reasons"):
        raise QAHardBlockError("Cannot render because qa_summary.json contains hard fail reasons")

    factuality = _load_json_for_gate(
        state.qa.get("factuality_report_path"),
        "factuality_report.json",
    )
    if int(factuality.get("blocked_count", 0) or 0) > 0:
        raise QAHardBlockError("Cannot render because factuality_report.json contains blocked claims")
    if int(factuality.get("disputed_count", 0) or 0) > 0:
        raise QAHardBlockError("Cannot render because factuality_report.json contains disputed claims")

    unresolved = [
        item for item in state.citations.get("citation_audit", [])
        if not item.get("resolved", False)
    ]
    if unresolved:
        raise QAHardBlockError("Cannot render because unresolved citations remain")


def _run_nodes_with_render_gate(state: ReportState, nodes: list[tuple[str, object]]) -> ReportState:
    render_names = {name for name, _ in render_nodes()}
    first_render_index = next(
        (index for index, (name, _) in enumerate(nodes) if name in render_names),
        None,
    )
    if first_render_index is None:
        return _run_nodes(state, nodes)

    state = _run_nodes(state, nodes[:first_render_index])
    if state.status != "validated":
        state.update_status("validated")
        state.checkpoint("VALIDATED")
    _assert_render_ready(state)
    return _run_nodes(state, nodes[first_render_index:])

def validate_workflow(job_id: str, *, deep_audit: bool = False, workspace_root: str | None = None) -> ReportState:
    """Validate agent-authored artifacts for an existing prepared run."""
    state = ReportState.resume(job_id, workspace_root=workspace_root)
    if deep_audit:
        state.flags["deep_audit"] = True
    state = _run_nodes(state, validate_nodes())
    state.update_status("validated")
    state.checkpoint("VALIDATED")
    return state


def validate_workflow_dry_run(job_id: str, *, deep_audit: bool = False, workspace_root: str | None = None) -> ReportState:
    """Simulate validation without writing checkpoints.

    Use this to pre-check if validate will pass before committing changes.
    Raises QAHardBlockError with detailed diagnostics if validation would fail.
    """
    from copy import deepcopy

    state = ReportState.resume(job_id, workspace_root=workspace_root)
    if deep_audit:
        state.flags["deep_audit"] = True
    # Work on a copy to avoid modifying the real state
    state_copy = deepcopy(state)

    # Track which stages would be run
    stages = validate_stages()
    print(f"[DRY-RUN] Simulating {len(stages)} validate stages for job {job_id} ...")

    dry_run_errors = []

    for stage in stages:
        try:
            state_copy = stage.run(state_copy, emit_events=False)
            print(f"  [PASS] {stage.name}")
        except QAHardBlockError as e:
            print(f"  [FAIL] {stage.name}: {e}")
            dry_run_errors.append(f"{stage.name}: {e}")
        except Exception as e:
            print(f"  [ERROR] {stage.name}: {type(e).__name__}: {e}")
            dry_run_errors.append(f"{stage.name}: {type(e).__name__}: {e}")

    if dry_run_errors:
        print(f"\n[DRY-RUN] Validation would fail with {len(dry_run_errors)} error(s)")
        raise QAHardBlockError(
            "Dry-run validation failed: " + "; ".join(dry_run_errors[:3]),
            hint="Run 'report-workflow diagnose --job-id <id>' to see full diagnostics"
        )

    print(f"\n[DRY-RUN] All stages would pass.")
    print("  Note: This is a simulation - no checkpoint or job event was written.")
    return state_copy


def render_workflow(
    job_id: str,
    *,
    workspace_root: str | None = None,
    reference_docx: str | None = None,
) -> ReportState:
    """Render and package a validated report workflow.

    Args:
        reference_docx: optional user-supplied .docx whose styles, margins,
            and header/footer the rendered document should follow. Persists
            into the run's spec so later re-renders keep the same template.
    """
    state = ReportState.resume(job_id, workspace_root=workspace_root)
    if reference_docx:
        state.spec["reference_docx_path"] = str(Path(reference_docx).resolve())
    _assert_render_ready(state)
    return _run_nodes(state, render_nodes())


def status_workflow(job_id: str, *, workspace_root: str | None = None) -> ReportState:
    """Load the current workflow state."""
    return ReportState.resume(job_id, workspace_root=workspace_root)


def run_workflow(
    user_prompt: str,
    uploaded_files: list[str],
    output_dir: str | None = None,
    *,
    report_profile: str | None = None,
) -> ReportState:
    """Convenience run: prepare, then validate/render only if agent artifacts already exist."""
    state = prepare_workflow(user_prompt, uploaded_files, output_dir, report_profile=report_profile)
    state = validate_workflow(state.job_id)
    return render_workflow(state.job_id)


def resume_workflow(job_id: str, *, workspace_root: str | None = None) -> ReportState:
    """Resume a workflow from the latest checkpoint."""
    state = ReportState.resume(job_id, workspace_root=workspace_root)
    if state.status == "awaiting_agent_artifacts":
        state = _run_nodes(state, validate_nodes())
        state.update_status("validated")
        state.checkpoint("VALIDATED")
        _assert_render_ready(state)
        return _run_nodes(state, render_nodes())
    if state.status == "validated":
        _assert_render_ready(state)
        return _run_nodes(state, render_nodes())
    nodes = workflow_nodes()
    start_index = _start_index_for_resume(state, nodes)
    return _run_nodes_with_render_gate(state, nodes[start_index:])


# ------------------------------------------------------------------
# Step-level validation for 4-step Agent workflow
# ------------------------------------------------------------------
# Instead of requiring the Agent to produce all artifacts in one shot
# (claim_matrix + outline + section_drafts + sentence_map), these
# functions allow the Agent to submit and validate one artifact at a
# time, checkpointing after each step.
#
# Step 1: submit_claim_matrix  -> validates claim_matrix.json
# Step 2: submit_outline       -> validates outline.json
# Step 3: submit_drafts        -> validates section_drafts/*.md + sentence_map.jsonl
# Step 4: submit_and_publish   -> runs full validate + render
# ------------------------------------------------------------------


def validate_step_claim_matrix(job_id: str, *, workspace_root: str | None = None) -> ReportState:
    """Step 1: Validate only claim_matrix.json.

    Runs CLAIM_PLAN validation and checkpoints.
    Agent should create claim_matrix.json before calling this.
    """
    state = ReportState.resume(job_id, workspace_root=workspace_root)
    state.checkpoint("STEP_CLAIM_MATRIX")
    append_job_event(state, "STEP_CLAIM_MATRIX", "start", "running")

    try:
        from .nodes.claim_plan import run_claim_plan
        state = run_claim_plan(state)
        append_job_event(state, "STEP_CLAIM_MATRIX", "success", "step_1_complete")
        state.update_status("step_1_complete")
        state.checkpoint("STEP_CLAIM_MATRIX_DONE")
    except (QAHardBlockError, AgentWorkRequired) as e:
        state.runtime["error"] = f"STEP_CLAIM_MATRIX: {e}"
        append_job_event(state, "STEP_CLAIM_MATRIX", "failure", "failed", {"error": str(e)})
        state.checkpoint("STEP_CLAIM_MATRIX_FAILED")
        raise

    return state


def validate_step_outline(job_id: str, *, workspace_root: str | None = None) -> ReportState:
    """Step 2: Validate only outline.json.

    Runs OUTLINE_PLAN validation and checkpoints.
    Agent should create outline.json before calling this.
    Requires Step 1 (claim_matrix) to be complete.
    """
    state = ReportState.resume(job_id, workspace_root=workspace_root)

    # Check prerequisite
    if not state.plan.get("claim_matrix", {}).get("claims"):
        raise QAHardBlockError(
            "Step 2 requires Step 1 (claim_matrix) to be complete. "
            "Run submit_claim_matrix first."
        )

    state.checkpoint("STEP_OUTLINE")
    append_job_event(state, "STEP_OUTLINE", "start", "running")

    try:
        from .nodes.outline_plan import run_outline_plan
        state = run_outline_plan(state)
        append_job_event(state, "STEP_OUTLINE", "success", "step_2_complete")
        state.update_status("step_2_complete")
        state.checkpoint("STEP_OUTLINE_DONE")
    except (QAHardBlockError, AgentWorkRequired) as e:
        state.runtime["error"] = f"STEP_OUTLINE: {e}"
        append_job_event(state, "STEP_OUTLINE", "failure", "failed", {"error": str(e)})
        state.checkpoint("STEP_OUTLINE_FAILED")
        raise

    return state


def validate_step_drafts(job_id: str, *, workspace_root: str | None = None) -> ReportState:
    """Step 3: Validate section_drafts/*.md and sentence_map.jsonl.

    Runs SECTION_DRAFT validation and checkpoints.
    Agent should create all section draft files and sentence_map.jsonl
    before calling this.
    Requires Steps 1+2 (claim_matrix + outline) to be complete.
    """
    state = ReportState.resume(job_id, workspace_root=workspace_root)

    # Check prerequisites
    if not state.plan.get("claim_matrix", {}).get("claims"):
        raise QAHardBlockError(
            "Step 3 requires Step 1 (claim_matrix) to be complete."
        )
    outline = state.plan.get("outline", {})
    if not outline or not outline.get("sections"):
        raise QAHardBlockError(
            "Step 3 requires Step 2 (outline) to be complete. "
            "Run submit_outline first."
        )

    state.checkpoint("STEP_DRAFTS")
    append_job_event(state, "STEP_DRAFTS", "start", "running")

    try:
        from .nodes.section_draft import run_section_draft
        state = run_section_draft(state)
        append_job_event(state, "STEP_DRAFTS", "success", "step_3_complete")
        state.update_status("step_3_complete")
        state.checkpoint("STEP_DRAFTS_DONE")
    except (QAHardBlockError, AgentWorkRequired) as e:
        state.runtime["error"] = f"STEP_DRAFTS: {e}"
        append_job_event(state, "STEP_DRAFTS", "failure", "failed", {"error": str(e)})
        state.checkpoint("STEP_DRAFTS_FAILED")
        raise

    return state
