"""DOC_METADATA_GATE - assemble front matter and validate abstract.

CONSOLIDATED (post-retrospective refactor):
  - FRONT_MATTER_BUILD: assemble title page, author block, keywords (academic mode hard block)
  - ABSTRACT_CHECK: validate abstract structure, word count, sanity checks

FRONT_MATTER_BUILD must run first since abstract metadata depends on front matter.

Position: After PLAN_FREEZE, before METHODS_PROTOCOL_BUILD / FIGURE_BUILD.
"""
from ..state import ReportState
from .front_matter_build import run_front_matter_build
from .abstract_check import run_abstract_check


def run_doc_metadata_gate(state: ReportState) -> ReportState:
    """Build front matter then validate abstract.

    For academic_paper: FRONT_MATTER_BUILD hard-blocks on placeholder values.
    ABSTRACT_CHECK hard-blocks on malformed abstract (trailing ellipses,
    incomplete sentences, wrong word count, internal markers).
    """
    state = run_front_matter_build(state)
    state = run_abstract_check(state)
    return state
