"""PLAN_FREEZE - freeze thesis, RQs, contribution framing, and section plan.

CONSOLIDATED (post-retrospective refactor):
  - PAPER_SCOPE_FREEZE: freeze thesis + RQs + contribution framing + scope hash
  - SECTION_PLAN_FREEZE: freeze claim/outline plan + section contract hash

Both nodes compute stable hashes over their respective payloads for tamper detection.
They run sequentially because SECTION_PLAN_FREEZE needs the scope to be frozen first.

Position: After AGENT_ARTIFACT_INTAKE, before DOC_METADATA_GATE.
"""
from ..state import ReportState
from .paper_scope_freeze import run_paper_scope_freeze
from .section_plan_freeze import run_section_plan_freeze


def run_plan_freeze(state: ReportState) -> ReportState:
    """Freeze scope (thesis, RQs, contributions) then section plan (claims, outline).

    Calls run_paper_scope_freeze first, then run_section_plan_freeze.
    Both must succeed for the plan to be considered frozen.
    """
    state = run_paper_scope_freeze(state)
    state = run_section_plan_freeze(state)
    return state
