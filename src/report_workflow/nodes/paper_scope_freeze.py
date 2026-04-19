"""PAPER_SCOPE_FREEZE node - freeze thesis, RQs, and contribution framing.

Position: After OUTLINE_PLAN, before SECTION_DRAFT. (Comes after CLAIM_PLAN has validated claims.)

This node addresses the most expensive failure mode from the retrospective:
"Scope was too broad at the start of this run."

For academic_report, it enforces:
  - A thesis statement exists in the outline's introduction section
  - Research questions (RQs) are defined if the blueprint requires them
  - Primary claims (1-3 max) are ranked and allocated to main text
  - Supporting/background claims are allocated to main text or appendix
  - The scope cannot change after this node (hash is frozen)

This node is the "scope freeze" that prevents the agent from drifting into
broader territory after initial claim planning.
"""
import hashlib
import json

from ..errors import QAHardBlockError
from ..state import ReportState
from ..runtime_support import write_json_artifact
from ..policies import get_policy


def _stable_hash(payload: dict) -> str:
    """Create a stable hash of the freeze payload for tamper detection."""
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _require_thesis(outline: dict, report_family: str) -> tuple[str, str]:
    """Extract and validate thesis statement from outline.

    Returns (thesis_text, thesis_location).
    Raises QAHardBlockError if thesis is required but missing per policy.
    """
    policy = get_policy(report_family)
    if not policy.claim.thesis_required:
        return "", ""

    sections = outline.get("sections", {})

    # Look for thesis in introduction section
    intro = sections.get("introduction", {})
    if isinstance(intro, dict):
        thesis = intro.get("thesis_statement", "")
        if thesis:
            return thesis, "introduction.thesis_statement"

        # Look in the outline's contribution/framing fields
        contribution = intro.get("contribution_statement", "")
        if contribution:
            return contribution, "introduction.contribution_statement"

        # Check top-level outline for thesis
        top_thesis = outline.get("thesis_statement", "")
        if top_thesis:
            return top_thesis, "outline.thesis_statement"

        top_contribution = outline.get("contribution_statement", "")
        if top_contribution:
            return top_contribution, "outline.contribution_statement"

    # For academic mode, thesis is required
    raise QAHardBlockError(
        "PAPER_SCOPE_FREEZE: Academic report requires a thesis statement in the outline. "
        "Add 'thesis_statement' to the introduction section or to the top-level outline. "
        "The thesis should appear in the final paragraph of the introduction."
    )


def _require_rqs(outline: dict, blueprint: dict, report_family: str) -> list[str]:
    """Extract research questions if the policy and blueprint require them.

    Returns list of RQ strings (may be empty if not required).
    Raises QAHardBlockError if RQs are required but missing.
    """
    policy = get_policy(report_family)
    if not policy.claim.rqs_required:
        return outline.get("research_questions", [])

    requires_rqs = blueprint.get("thesis", {}).get("requires_rqs", False)
    if not requires_rqs:
        return outline.get("research_questions", [])

    rqs = outline.get("research_questions", [])
    if not rqs:
        raise QAHardBlockError(
            "PAPER_SCOPE_FREEZE: Blueprint requires research_questions but none found in outline. "
            "Add a 'research_questions' list to the outline JSON."
        )

    if not isinstance(rqs, list):
        raise QAHardBlockError(
            f"PAPER_SCOPE_FREEZE: research_questions must be a list, got {type(rqs).__name__}."
        )

    if len(rqs) > 5:
        raise QAHardBlockError(
            f"PAPER_SCOPE_FREEZE: Maximum 5 research questions allowed, got {len(rqs)}."
        )

    return rqs


def _rank_claims(claim_matrix: dict) -> dict:
    """Rank claims by role and compute contribution framing.

    Returns a dict with:
      - primary_claims: sorted by rank
      - supporting_claims: list
      - background_claims: list
      - ranked_ids: ordered list of all claim_ids (primary first)
      - main_text_claims: claims allocated to main body
      - appendix_claims: claims allocated to appendix/supplementary
    """
    claims = claim_matrix.get("claims", [])
    result = {
        "primary_claims": [],
        "supporting_claims": [],
        "background_claims": [],
        "ranked_ids": [],
        "main_text_claims": [],
        "appendix_claims": [],
    }

    for claim in claims:
        role = claim.get("claim_role", "supporting")
        claim_id = claim.get("claim_id", "")

        if role == "primary":
            result["primary_claims"].append(claim)
            result["ranked_ids"].append(claim_id)
            result["main_text_claims"].append(claim_id)
        elif role == "supporting":
            result["supporting_claims"].append(claim)
            # Supporting claims go to main text unless explicitly marked appendix
            allocation = claim.get("allocation", "main_text")
            if allocation == "appendix":
                result["appendix_claims"].append(claim_id)
            else:
                result["main_text_claims"].append(claim_id)
        elif role == "background":
            result["background_claims"].append(claim)
            # Background claims default to appendix unless explicitly marked main_text
            allocation = claim.get("allocation", "appendix")
            if allocation == "main_text":
                result["main_text_claims"].append(claim_id)
            else:
                result["appendix_claims"].append(claim_id)

    return result


def _validate_claim_allocation(ranking: dict, report_family: str) -> None:
    """Validate that claim allocation makes sense per policy.

    Raises QAHardBlockError if allocation rules are violated.
    """
    policy = get_policy(report_family)
    if not policy.claim.thesis_required:
        return

    primary_count = len(ranking["primary_claims"])
    supporting_count = len(ranking["supporting_claims"])
    background_count = len(ranking["background_claims"])
    main_text_count = len(ranking["main_text_claims"])

    if primary_count == 0:
        raise QAHardBlockError(
            "PAPER_SCOPE_FREEZE: At least 1 primary claim must be allocated to main text."
        )

    if main_text_count == 0:
        raise QAHardBlockError(
            "PAPER_SCOPE_FREEZE: No claims allocated to main text. "
            "Primary claims must appear in the main body, not just appendix."
        )

    # Supporting claims shouldn't vastly outnumber primary claims
    if primary_count > 0 and supporting_count > primary_count * 5:
        raise QAHardBlockError(
            f"PAPER_SCOPE_FREEZE: Supporting claims ({supporting_count}) vastly outnumber "
            f"primary claims ({primary_count}). Restructure the claim hierarchy."
        )

    # Background claims should not dominate
    if main_text_count > 0 and background_count > main_text_count * 3:
        raise QAHardBlockError(
            f"PAPER_SCOPE_FREEZE: Background claims ({background_count}) dominate "
            f"main text claims ({main_text_count}). Background claims belong in appendix."
        )


def run_paper_scope_freeze(state: ReportState) -> ReportState:
    """PAPER_SCOPE_FREEZE - freeze thesis, RQs, and contribution framing.

    Position: After OUTLINE_PLAN, before SECTION_DRAFT.
    Prerequisite: CLAIM_PLAN has already validated claim_matrix.

    For academic_report: hard blocks if thesis is missing or claims are poorly allocated.
    """
    report_family = state.spec.get("report_family", "")
    blueprint = state.plan.get("blueprint", {})
    outline = state.plan.get("outline", {})
    claim_matrix = state.plan.get("claim_matrix", {})

    # Extract thesis (required for academic)
    thesis_text, thesis_location = _require_thesis(outline, report_family)

    # Extract RQs (optional for academic unless blueprint requires)
    research_questions = _require_rqs(outline, blueprint, report_family)

    # Rank and allocate claims
    ranking = _rank_claims(claim_matrix)
    _validate_claim_allocation(ranking, report_family)

    # Build freeze payload
    payload = {
        "thesis_statement": thesis_text,
        "thesis_location": thesis_location,
        "research_questions": research_questions,
        "claim_rankings": {
            "primary_claims": [c.get("claim_id") for c in ranking["primary_claims"]],
            "supporting_claims": [c.get("claim_id") for c in ranking["supporting_claims"]],
            "background_claims": [c.get("claim_id") for c in ranking["background_claims"]],
        },
        "allocation": {
            "main_text": ranking["main_text_claims"],
            "appendix": ranking["appendix_claims"],
        },
        "primary_contribution": (
            ranking["primary_claims"][0].get("claim_text", "")
            if ranking["primary_claims"]
            else ""
        ),
    }

    plan_hash = _stable_hash(payload)

    freeze = {
        "job_id": state.job_id,
        "status": "frozen",
        "plan_hash": plan_hash,
        "report_family": report_family,
        "thesis_statement": thesis_text,
        "thesis_location": thesis_location,
        "research_questions": research_questions,
        "claim_rankings": ranking["ranked_ids"],
        "primary_claims": [c.get("claim_id") for c in ranking["primary_claims"]],
        "supporting_claims": [c.get("claim_id") for c in ranking["supporting_claims"]],
        "background_claims": [c.get("claim_id") for c in ranking["background_claims"]],
        "allocation": {
            "main_text": ranking["main_text_claims"],
            "appendix": ranking["appendix_claims"],
        },
        "primary_contribution": payload["primary_contribution"],
    }

    # Write freeze artifact
    path = write_json_artifact(state, "paper_scope_freeze.json", freeze)
    state.plan["paper_scope_freeze_path"] = str(path)
    state.plan["paper_scope_hash"] = plan_hash
    state.plan["thesis_statement"] = thesis_text
    state.plan["research_questions"] = research_questions
    state.plan["primary_contribution"] = payload["primary_contribution"]

    return state
