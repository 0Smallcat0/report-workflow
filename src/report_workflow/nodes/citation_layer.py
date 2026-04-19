"""CITATION_LAYER - bind citations and verify references.

CONSOLIDATED (post-retrospective refactor):
  - CITATION_BIND: resolve [CITE:...] placeholders to full citations from evidence_ledger
  - REFERENCE_VERIFY: verify DOI/arXiv links resolve (academic mode hard block)

CITATION_BIND must run first since REFERENCE_VERIFY validates the resolved references.

Position: After DRAFT_ASSEMBLY, before FACTUALITY_CHECK.
"""
from ..state import ReportState
from .citation_bind import run_citation_bind
from .reference_verify import run_reference_verify


def run_citation_layer(state: ReportState) -> ReportState:
    """Bind citations then verify reference links.

    CITATION_BIND strips [CITE:...] placeholders and replaces them with
    inline citations from the evidence ledger.
    REFERENCE_VERIFY checks that all DOI/arXiv URLs resolve (hard block for academic).
    """
    state = run_citation_bind(state)
    state = run_reference_verify(state)
    return state
