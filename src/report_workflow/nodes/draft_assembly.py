"""DRAFT_ASSEMBLY - apply revisions and assemble publication draft.

CONSOLIDATED (post-retrospective refactor):
  - REVISION_APPLY: apply revision_plan.json to base_document (revise_existing only)
  - MERGE_DRAFT: concatenate sections in blueprint order + strip artifacts

For new_draft: REVISION_APPLY is a no-op; MERGE_DRAFT builds from section files.
For revise_existing: REVISION_APPLY writes merged_draft_md; MERGE_DRAFT reads it
  and does artifact stripping (audit tables, [CITE:] markers, internal paths).

MERGE_DRAFT absorbs:
  - results_sanity_pass (audit table removal)
  - main_text_artifact_filter (marker stripping, structural artifact scanning)

Position: After SECTION_DRAFT + FIGURE_BUILD + METHODS_PROTOCOL_BUILD, before SECTION_ROLE_CHECK.
"""
from ..state import ReportState
from .revision_apply import run_revision_apply
from .merge_draft import run_merge_draft


def run_draft_assembly(state: ReportState) -> ReportState:
    """Apply revisions (if any) and assemble the cleaned publication draft.

    REVISION_APPLY runs first (no-op for new_draft workflows).
    MERGE_DRAFT always runs to ensure artifact-free publication draft.
    """
    state = run_revision_apply(state)
    state = run_merge_draft(state)
    return state
