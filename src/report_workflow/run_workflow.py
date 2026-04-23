"""Main workflow orchestrator."""
import json
import sys
from .state import ReportState, WORKFLOW_RUNS_DIR
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
from .nodes.notebook_sync import run_notebook_sync
from .nodes.agent_tasks import run_agent_task_briefs
from .nodes.agent_artifact_intake import run_agent_artifact_intake
from .nodes.plan_freeze import run_plan_freeze
from .nodes.doc_metadata_gate import run_doc_metadata_gate
from .nodes.figure_build import run_figure_build
from .nodes.figure_quality import run_figure_quality
from .nodes.methods_protocol_build import run_methods_protocol_build
from .nodes.draft_assembly import run_draft_assembly
from .nodes.project_identity_gate import run_project_identity_gate
from .nodes.admissions_tone_gate import run_admissions_tone_gate
from .nodes.section_role_check import run_section_role_check
from .nodes.citation_layer import run_citation_layer
from .nodes.factuality_check import run_factuality_check
from .nodes.research_execute import run_research_execute
from .nodes.claim_verify_execute import run_claim_verify_execute
from .nodes.consistency_check import run_consistency_check  # kept for explicit quality command
from .nodes.guideline_check import run_guideline_check      # kept for explicit quality command
from .nodes.base_document_parse import run_base_document_parse
from .nodes.qa_gate import run_qa_gate
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


def workflow_nodes() -> list[tuple[str, object]]:
    """Return the legacy full ordered workflow node list."""
    return prepare_nodes() + validate_nodes() + render_nodes()


def prepare_nodes() -> list[tuple[str, object]]:
    """Return nodes that prepare deterministic source/evidence artifacts."""
    return [
        ("INTAKE", run_intake),
        ("GUIDELINE_SELECT", run_guideline_select),
        ("BLUEPRINT_PLAN", run_blueprint_plan),
        ("CORPUS_BUILD", run_corpus_build),
        ("SOURCE_PARSE", run_source_parse),
        ("BASE_DOCUMENT_PARSE", run_base_document_parse),
        ("EVIDENCE_NORMALIZE", run_evidence_normalize),
        ("EVIDENCE_STORE", run_evidence_store),
        ("NOTEBOOK_SYNC", run_notebook_sync),
        ("AGENT_TASKS", run_agent_task_briefs),
    ]


def validate_nodes() -> list[tuple[str, object]]:
    """Return nodes that validate external agent-produced artifacts.

    Simplified pipeline (17 → 11 nodes, post-retrospective refactor):
    - AGENT_ARTIFACT_INTAKE: CLAIM_PLAN + OUTLINE_PLAN + SECTION_DRAFT combined
    - PLAN_FREEZE: PAPER_SCOPE_FREEZE + SECTION_PLAN_FREEZE combined
    - DOC_METADATA_GATE: FRONT_MATTER_BUILD + ABSTRACT_CHECK combined
    - DRAFT_ASSEMBLY: REVISION_APPLY + MERGE_DRAFT combined
      (MERGE_DRAFT absorbs: results_sanity_pass + main_text_artifact_filter)
    - CITATION_LAYER: CITATION_BIND + REFERENCE_VERIFY combined
    - FIGURE_QUALITY: absorbs caption_interpreter + figure_contract_check
    - GUIDELINE_CHECK and CONSISTENCY_CHECK moved to explicit quality commands
      (run via: report-workflow check-quality --job-id <id>)
    """
    return [
        ("AGENT_ARTIFACT_INTAKE", run_agent_artifact_intake),
        ("PLAN_FREEZE", run_plan_freeze),
        ("DOC_METADATA_GATE", run_doc_metadata_gate),
        ("METHODS_PROTOCOL_BUILD", run_methods_protocol_build),
        ("FIGURE_BUILD", run_figure_build),
        ("DRAFT_ASSEMBLY", run_draft_assembly),
        ("PROJECT_IDENTITY_GATE", run_project_identity_gate),
        ("ADMISSIONS_TONE_GATE", run_admissions_tone_gate),
        ("SECTION_ROLE_CHECK", run_section_role_check),
        ("CITATION_LAYER", run_citation_layer),
        ("FACTUALITY_CHECK", run_factuality_check),
        ("RESEARCH_EXECUTE", run_research_execute),
        ("CLAIM_VERIFY_EXECUTE", run_claim_verify_execute),
        ("FIGURE_QUALITY", run_figure_quality),
        ("QA_GATE", run_qa_gate),
    ]


def render_nodes() -> list[tuple[str, object]]:
    """Return nodes that render and package a validated workflow."""
    return [
        ("STYLE_PASS", run_style_pass),
        ("PUBLICATION_NATURALNESS_PASS", run_publication_naturalness_pass),
        ("ADMISSIONS_MONOGRAPH_POLISH", run_admissions_monograph_polish),
        ("HEADING_CONTRACT_CHECK", run_heading_contract_check),
        ("DOCX_RENDER", run_docx_render),
        ("POST_RENDER_REPAIR", run_post_render_repair),
        ("POST_RENDER_VALIDATE", run_post_render_validate),
        ("VISUAL_RENDER_CHECK", run_visual_render_check),
        ("REFERENCE_REALITY_CHECK", run_reference_reality_check),
        ("REFERENCE_RELEVANCE_GATE", run_reference_relevance_gate),
        ("SOURCE_APPENDIX_RENDER", run_source_appendix_render),
        ("FINAL_PUBLISH", run_final_publish),
        ("SUPPLEMENTARY_PACKAGE_BUILD", run_supplementary_package_build),
        ("ARTIFACTS", run_artifacts),
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
        return 0


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
    output_dir: str,
    *,
    report_family: str | None = None,
    report_family_detail: str | None = None,
    intent: str = "new_draft",
    artifact_role_map: dict[str, str] | None = None,
    front_matter: dict | None = None,
    project_identity: dict | None = None,
) -> ReportState:
    """Prepare deterministic artifacts and agent task briefs.

    Args:
        intent: 'new_draft' or 'revise_existing'.
        artifact_role_map: mapping from file name to artifact role
            ('source_data' or 'base_document').
    """
    state = ReportState.new(user_prompt, uploaded_files, output_dir)
    if report_family:
        state.spec["report_family_override"] = report_family
    if report_family_detail:
        state.spec["report_family_detail"] = report_family_detail
    state.spec["task_intent"] = intent
    if artifact_role_map:
        state.spec["artifact_role_map"] = artifact_role_map
    if front_matter:
        state.spec["front_matter"] = front_matter
    if project_identity:
        state.spec["project_identity"] = project_identity
        identity_path = WORKFLOW_RUNS_DIR / state.job_id / "project_identity.json"
        identity_path.write_text(json.dumps(project_identity, indent=2), encoding="utf-8")
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

def validate_workflow(job_id: str, *, deep_audit: bool = False) -> ReportState:
    """Validate agent-authored artifacts for an existing prepared run."""
    state = ReportState.resume(job_id)
    if deep_audit:
        state.flags["deep_audit"] = True
    state = _run_nodes(state, validate_nodes())
    state.update_status("validated")
    state.checkpoint("VALIDATED")
    return state


def validate_workflow_dry_run(job_id: str, *, deep_audit: bool = False) -> ReportState:
    """Simulate validation without writing checkpoints.

    Use this to pre-check if validate will pass before committing changes.
    Raises QAHardBlockError with detailed diagnostics if validation would fail.
    """
    from copy import deepcopy

    state = ReportState.resume(job_id)
    if deep_audit:
        state.flags["deep_audit"] = True
    # Work on a copy to avoid modifying the real state
    state_copy = deepcopy(state)

    # Track which nodes would be run
    nodes = validate_nodes()
    print(f"[DRY-RUN] Simulating {len(nodes)} validate nodes for job {job_id} ...")

    dry_run_errors = []

    for node_name, node_fn in nodes:
        try:
            state_copy = node_fn(state_copy)
            print(f"  [PASS] {node_name}")
        except QAHardBlockError as e:
            print(f"  [FAIL] {node_name} — {e}")
            dry_run_errors.append(f"{node_name}: {e}")
        except Exception as e:
            print(f"  [ERROR] {node_name} — {type(e).__name__}: {e}")
            dry_run_errors.append(f"{node_name}: {type(e).__name__}: {e}")

    if dry_run_errors:
        print(f"\n[DRY-RUN] Validation would fail with {len(dry_run_errors)} error(s)")
        raise QAHardBlockError(
            "Dry-run validation failed: " + "; ".join(dry_run_errors[:3]),
            hint="Run 'report-workflow diagnose --job-id <id>' to see full diagnostics"
        )

    print(f"\n[DRY-RUN] All nodes would pass.")
    print("  Note: This is a simulation - no checkpoint was written.")
    return state_copy


def render_workflow(job_id: str) -> ReportState:
    """Render and package a validated report workflow."""
    state = ReportState.resume(job_id)
    if state.qa.get("qa_decision") != "pass":
        raise QAHardBlockError("Cannot render before validate produces qa_decision=pass")
    return _run_nodes(state, render_nodes())


def status_workflow(job_id: str) -> ReportState:
    """Load the current workflow state."""
    return ReportState.resume(job_id)


def run_workflow(
    user_prompt: str,
    uploaded_files: list[str],
    output_dir: str,
    *,
    report_family: str | None = None,
) -> ReportState:
    """Convenience run: prepare, then validate/render only if agent artifacts already exist."""
    state = prepare_workflow(user_prompt, uploaded_files, output_dir, report_family=report_family)
    state = validate_workflow(state.job_id)
    return render_workflow(state.job_id)


def resume_workflow(job_id: str) -> ReportState:
    """Resume a workflow from the latest checkpoint."""
    state = ReportState.resume(job_id)
    if state.status == "awaiting_agent_artifacts":
        return _run_nodes(state, validate_nodes() + render_nodes())
    if state.status == "validated":
        return _run_nodes(state, render_nodes())
    nodes = workflow_nodes()
    start_index = _start_index_for_resume(state, nodes)
    return _run_nodes(state, nodes[start_index:])


# ------------------------------------------------------------------
# Step-level validation for 4-step Agent workflow
# ------------------------------------------------------------------
# Instead of requiring the Agent to produce all artifacts in one shot
# (claim_matrix + outline + section_drafts + sentence_map), these
# functions allow the Agent to submit and validate one artifact at a
# time, checkpointing after each step.
#
# Step 1: submit_claim_matrix  → validates claim_matrix.json
# Step 2: submit_outline       → validates outline.json
# Step 3: submit_drafts        → validates section_drafts/*.md + sentence_map.jsonl
# Step 4: submit_and_publish   → runs full validate + render
# ------------------------------------------------------------------


def validate_step_claim_matrix(job_id: str) -> ReportState:
    """Step 1: Validate only claim_matrix.json.

    Runs CLAIM_PLAN validation and checkpoints.
    Agent should create claim_matrix.json before calling this.
    """
    state = ReportState.resume(job_id)
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


def validate_step_outline(job_id: str) -> ReportState:
    """Step 2: Validate only outline.json.

    Runs OUTLINE_PLAN validation and checkpoints.
    Agent should create outline.json before calling this.
    Requires Step 1 (claim_matrix) to be complete.
    """
    state = ReportState.resume(job_id)

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


def validate_step_drafts(job_id: str) -> ReportState:
    """Step 3: Validate section_drafts/*.md and sentence_map.jsonl.

    Runs SECTION_DRAFT validation and checkpoints.
    Agent should create all section draft files and sentence_map.jsonl
    before calling this.
    Requires Steps 1+2 (claim_matrix + outline) to be complete.
    """
    state = ReportState.resume(job_id)

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
