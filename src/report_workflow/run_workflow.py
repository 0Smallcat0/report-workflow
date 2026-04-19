"""Main workflow orchestrator."""
import sys
from .state import ReportState
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
from .nodes.agent_tasks import run_agent_task_briefs
from .nodes.agent_artifact_intake import run_agent_artifact_intake
from .nodes.plan_freeze import run_plan_freeze
from .nodes.doc_metadata_gate import run_doc_metadata_gate
from .nodes.figure_build import run_figure_build
from .nodes.figure_quality import run_figure_quality
from .nodes.methods_protocol_build import run_methods_protocol_build
from .nodes.draft_assembly import run_draft_assembly
from .nodes.section_role_check import run_section_role_check
from .nodes.citation_layer import run_citation_layer
from .nodes.factuality_check import run_factuality_check
from .nodes.consistency_check import run_consistency_check  # kept for explicit quality command
from .nodes.guideline_check import run_guideline_check      # kept for explicit quality command
from .nodes.base_document_parse import run_base_document_parse
from .nodes.qa_gate import run_qa_gate
from .nodes.style_pass import run_style_pass
from .nodes.section_role_check import run_section_role_check
from .nodes.source_appendix_render import run_source_appendix_render
from .nodes.docx_render import run_docx_render
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
        ("SECTION_ROLE_CHECK", run_section_role_check),
        ("CITATION_LAYER", run_citation_layer),
        ("FACTUALITY_CHECK", run_factuality_check),
        ("FIGURE_QUALITY", run_figure_quality),
        ("QA_GATE", run_qa_gate),
    ]


def render_nodes() -> list[tuple[str, object]]:
    """Return nodes that render and package a validated workflow."""
    return [
        ("STYLE_PASS", run_style_pass),
        ("DOCX_RENDER", run_docx_render),
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
    intent: str = "new_draft",
    artifact_role_map: dict[str, str] | None = None,
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
    state.spec["task_intent"] = intent
    if artifact_role_map:
        state.spec["artifact_role_map"] = artifact_role_map
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


def validate_workflow(job_id: str) -> ReportState:
    """Validate agent-authored artifacts for an existing prepared run."""
    state = ReportState.resume(job_id)
    state = _run_nodes(state, validate_nodes())
    state.update_status("validated")
    state.checkpoint("VALIDATED")
    return state


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
