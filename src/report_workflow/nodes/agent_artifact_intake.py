"""AGENT_ARTIFACT_INTAKE - validate all agent-authored artifacts.

CONSOLIDATED (post-retrospective refactor):
  - CLAIM_PLAN: validate claim_matrix.json structure and evidence linkage
  - OUTLINE_PLAN: validate outline.json against blueprint contract
  - SECTION_DRAFT: validate section_drafts/*.md files (non-empty, non-placeholder)

All three load agent-authored JSON/markdown artifacts and validate their structure
against the blueprint contract. They run sequentially because each builds on the prior.

Position: First node in validate phase, after AGENT_TASKS (prepare).
"""
from ..state import ReportState
from .claim_plan import run_claim_plan
from .outline_plan import run_outline_plan
from .section_draft import run_section_draft


def run_agent_artifact_intake(state: ReportState) -> ReportState:
    """Validate claim matrix, outline plan, and section drafts.

    Runs CLAIM_PLAN → OUTLINE_PLAN → SECTION_DRAFT sequentially.
    Each validates its artifact and populates state.plan or state.drafts.
    Any hard block aborts the entire pipeline.
    """
    state = run_claim_plan(state)
    state = run_outline_plan(state)
    state = run_section_draft(state)
    return state
