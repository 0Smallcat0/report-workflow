"""SECTION_PLAN_FREEZE - freeze planning artifacts before drafting."""
import hashlib
import json

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR
from .section_contract import section_requires_claims, validate_required_outline_sections


def _stable_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def run_section_plan_freeze(state: ReportState) -> ReportState:
    """Persist the exact claim/outline plan that SECTION_DRAFT must follow."""
    claim_matrix = state.plan.get("claim_matrix") or {}
    outline = state.plan.get("outline") or {}
    blueprint = state.plan.get("blueprint") or {}
    claims = claim_matrix.get("claims", [])
    sections = outline.get("sections", {})

    if not claims:
        raise QAHardBlockError("Cannot freeze section plan without claims")
    if not sections:
        raise QAHardBlockError("Cannot freeze section plan without outline sections")
    # In revise_existing the outline mirrors the base document's own sections:
    # blueprint-required sections do not apply, and sections the revision does
    # not touch legitimately carry no claims.
    revise_mode = state.spec.get("task_intent") == "revise_existing"
    if not revise_mode:
        validate_required_outline_sections(blueprint, sections)

    known_claim_ids = {claim.get("claim_id") for claim in claims if claim.get("claim_id")}
    assigned_claim_ids = set()
    for section_id, section in sections.items():
        claim_ids = section.get("claim_ids", [])
        if not claim_ids and not revise_mode and section_requires_claims(blueprint, section_id):
            raise QAHardBlockError(f"Outline section has no claims: {section_id}")
        assigned_claim_ids.update(claim_ids)

    unknown = sorted(claim_id for claim_id in assigned_claim_ids if claim_id not in known_claim_ids)
    if unknown:
        raise QAHardBlockError(f"Outline references unknown claims: {', '.join(unknown)}")

    missing = sorted(claim_id for claim_id in known_claim_ids if claim_id not in assigned_claim_ids)
    if missing:
        raise QAHardBlockError(f"Section plan does not cover claims: {', '.join(missing)}")

    payload = {
        "claim_matrix": claim_matrix,
        "outline": outline,
        "figure_table_plan_status": state.drafts.get("figure_table_plan_status", "not_enforced"),
    }
    freeze = {
        "job_id": state.job_id,
        "status": "frozen",
        "plan_hash": _stable_hash(payload),
        "claim_count": len(claims),
        "section_count": len(sections),
        "claims": sorted(known_claim_ids),
        "sections": sorted(sections.keys()),
        "payload": payload,
    }

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "section_plan_freeze.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(freeze, f, indent=2, default=str)

    state.plan["section_plan_freeze_path"] = str(path)
    state.plan["section_plan_hash"] = freeze["plan_hash"]
    return state
