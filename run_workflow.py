"""Main workflow orchestrator."""
import sys
from .state import ReportState
from .nodes.intake import run_intake
from .nodes.guideline_select import run_guideline_select
from .nodes.blueprint_plan import run_blueprint_plan
from .nodes.corpus_build import run_corpus_build
from .nodes.source_parse import run_source_parse
from .nodes.evidence_normalize import run_evidence_normalize
from .nodes.claim_plan import run_claim_plan
from .nodes.outline_plan import run_outline_plan
from .nodes.section_draft import run_section_draft
from .nodes.merge_draft import run_merge_draft
from .nodes.citation_bind import run_citation_bind
from .nodes.factuality_check import run_factuality_check, QAHardBlockError
from .nodes.qa_gate import run_qa_gate
from .nodes.docx_render import run_docx_render
from .nodes.final_publish import run_final_publish
from .nodes.phase2_wrappers import (
    run_consistency_check_wrapper,
    run_style_lint_wrapper,
    run_guideline_check_wrapper,
    run_figure_table_plan_wrapper,
    run_research_retrieve_wrapper,
)
from .nodes.waiver_governance import run_waiver_governance
from .nodes.revision_apply import run_revision_apply
from .nodes.artifacts import run_artifacts


def run_workflow(user_prompt: str, uploaded_files: list[str], output_dir: str) -> ReportState:
    """Run the complete report workflow.
    
    Args:
        user_prompt: The user's request
        uploaded_files: List of uploaded file paths
        output_dir: Directory for output files
    
    Returns:
        ReportState with all fields populated
    """
    state = ReportState.new(user_prompt, uploaded_files, output_dir)
    
    nodes = [
        ("INTAKE", run_intake),
        ("GUIDELINE_SELECT", run_guideline_select),
        ("BLUEPRINT_PLAN", run_blueprint_plan),
        ("CORPUS_BUILD", run_corpus_build),
        ("SOURCE_PARSE", run_source_parse),
        ("EVIDENCE_NORMALIZE", run_evidence_normalize),
        ("CLAIM_PLAN", run_claim_plan),
        ("OUTLINE_PLAN", run_outline_plan),
        ("SECTION_DRAFT", run_section_draft),
        ("MERGE_DRAFT", run_merge_draft),
        ("CITATION_BIND", run_citation_bind),
        ("FACTUALITY_CHECK", run_factuality_check),
        ("CONSISTENCY_CHECK", run_consistency_check_wrapper),
        ("STYLE_LINT", run_style_lint_wrapper),
        ("GUIDELINE_CHECK", run_guideline_check_wrapper),
        ("QA_GATE", run_qa_gate),
        ("WAIVER_GOVERNANCE", run_waiver_governance),
        ("REVISION_APPLY", run_revision_apply),
        ("FIGURE_TABLE_PLAN", run_figure_table_plan_wrapper),
        ("DOCX_RENDER", run_docx_render),
        ("ARTIFACTS", run_artifacts),
        ("FINAL_PUBLISH", run_final_publish),
    ]
    
    for node_name, node_fn in nodes:
        state.checkpoint(node_name)
        try:
            state = node_fn(state)
        except QAHardBlockError as e:
            print(f"[WORKFLOW] Node {node_name!r} raised QAHardBlockError: {e}", file=sys.stderr)
            state.status = "failed"
            state.checkpoint("FAILED")
            raise
        except Exception as e:
            print(f"[WORKFLOW] Node {node_name!r} failed with {type(e).__name__}: {e}", file=sys.stderr)
            state.status = "failed"
            state.checkpoint("FAILED")
            raise
    
    return state
