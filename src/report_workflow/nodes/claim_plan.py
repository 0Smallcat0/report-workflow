"""CLAIM_PLAN node - load and validate agent-produced claim_matrix.json.

IMPORTANT: claim_matrix.json on disk is the CANONICAL source read by factuality_check.
The CLAIM_PLAN node loads it here, validates it, and embeds it in state.plan.claim_matrix.
But factuality_check.py reads claim_matrix.json DIRECTLY from disk (not from state.plan).
Therefore: editing checkpoint files to change claim evidence_ids or claim_texts has NO EFFECT.
Always edit ~/.hermes/workflow_runs/<job_id>/claim_matrix.json directly.
"""
import json
from pathlib import Path

from ..errors import AgentWorkRequired, QAHardBlockError
from ..runtime_support import run_dir_for, write_json_artifact
from ..state import ReportState
from ..policies import get_policy
from .agent_tasks import write_agent_task_briefs


def _claim_matrix_path(state: ReportState) -> Path:
    return run_dir_for(state) / "claim_matrix.json"


def _load_claim_matrix(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise QAHardBlockError(f"Malformed claim_matrix.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise QAHardBlockError("claim_matrix.json must contain a JSON object")
    return payload


def _validate_claim_matrix(payload: dict, report_family: str = "") -> list[dict]:
    claims = payload.get("claims", [])
    if not isinstance(claims, list) or not claims:
        raise QAHardBlockError("claim_matrix.json must contain a non-empty claims list")

    seen = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise QAHardBlockError(f"claim_matrix claims[{index}] must be an object")
        claim_id = claim.get("claim_id")
        if not claim_id:
            raise QAHardBlockError(f"claim_matrix claims[{index}] is missing claim_id")
        if claim_id in seen:
            raise QAHardBlockError(f"Duplicate claim_id in claim_matrix: {claim_id}")
        seen.add(claim_id)
        if not claim.get("claim_text"):
            raise QAHardBlockError(f"Claim {claim_id} is missing claim_text")
        evidence_ids = claim.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise QAHardBlockError(f"Claim {claim_id} must include at least one evidence_id")
        claim.setdefault("claim_type", "factual")
        claim.setdefault("status", "supported")

    # ------------------------------------------------------------------
    # Claim role validation per policy.
    # claim_role must be present and must be one of: primary, supporting, background.
    # Max 3 primary claims. All primary claims must directly support the
    # primary contribution (enforced by PAPER_SCOPE_FREEZE later).
    # ------------------------------------------------------------------
    policy = get_policy(report_family)
    if policy.claim.role_validation_required:
        VALID_ROLES = {"primary", "supporting", "background"}
        role_counts = {"primary": 0, "supporting": 0, "background": 0}
        for claim in claims:
            role = claim.get("claim_role", "")
            if not role:
                raise QAHardBlockError(
                    f"Claim {claim.get('claim_id')} is missing 'claim_role' field. "
                    f"Academic reports require claim_role: {' | '.join(VALID_ROLES)}."
                )
            if role not in VALID_ROLES:
                raise QAHardBlockError(
                    f"Claim {claim.get('claim_id')} has invalid claim_role: {role!r}. "
                    f"Must be one of: {' '.join(VALID_ROLES)}."
                )
            role_counts[role] = role_counts.get(role, 0) + 1

        if role_counts.get("primary", 0) == 0:
            raise QAHardBlockError(
                "At least 1 primary claim is required for academic_report. "
                "No primary claims found in claim_matrix."
            )
        if role_counts.get("primary", 0) > 3:
            raise QAHardBlockError(
                f"Maximum 3 primary claims allowed for academic_report, "
                f"found {role_counts['primary']}. Move extra claims to supporting or background."
            )

    return claims


def run_claim_plan(state: ReportState) -> ReportState:
    """T8: CLAIM_PLAN - load agent-authored claim matrix."""
    path = _claim_matrix_path(state)
    if not path.exists():
        write_agent_task_briefs(state)
        state.runtime["required_agent_artifacts"] = [str(path)]
        state.update_status("awaiting_agent_artifacts")
        raise AgentWorkRequired(f"Agent artifact required: {path}", [str(path)])

    claim_matrix = _load_claim_matrix(path)
    report_family = state.spec.get("report_family", "")
    claims = _validate_claim_matrix(claim_matrix, report_family=report_family)
    state.plan["claim_matrix"] = {"claims": claims}
    state.plan["claim_matrix_path"] = write_json_artifact(state, "claim_matrix.json", state.plan["claim_matrix"])
    return state
