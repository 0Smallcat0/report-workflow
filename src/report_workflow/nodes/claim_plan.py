"""CLAIM_PLAN node - load and validate agent-produced claim_matrix.json.

IMPORTANT: claim_matrix.json on disk is the CANONICAL source read by factuality_check.
The CLAIM_PLAN node loads it here, validates it, and embeds it in state.plan.claim_matrix.
But factuality_check.py reads claim_matrix.json DIRECTLY from disk (not from state.plan).
Therefore: editing checkpoint files to change claim evidence_ids or claim_texts has NO EFFECT.
Always edit the current run directory's claim_matrix.json directly.
"""
import json
from pathlib import Path

from ..errors import AgentWorkRequired, QAHardBlockError
from ..runtime_support import run_dir_for, write_json_artifact
from ..state import ReportState
from ..policies import get_policy
from ..artifact_contract import load_jsonl_without_contract, make_artifact_contract, validate_artifact_contract, write_artifact_contract
from ..artifact_contract import validate_evidence_ledger_provenance
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


def _validate_claim_matrix(payload: dict, report_profile: str = "") -> list[dict]:
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
    policy = get_policy(report_profile)
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
                "At least 1 primary claim is required for academic_paper. "
                "No primary claims found in claim_matrix."
            )
        if role_counts.get("primary", 0) > 3:
            raise QAHardBlockError(
                f"Maximum 3 primary claims allowed for academic_paper, "
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
    validate_artifact_contract(state, path, allow_missing=True)
    report_profile = state.spec.get("report_profile", "")
    claims = _validate_claim_matrix(claim_matrix, report_profile=report_profile)
    evidence_path = state.sources.get("evidence_ledger_path")
    known_evidence = {
        item.get("evidence_id")
        for item in load_jsonl_without_contract(evidence_path)
        if item.get("evidence_id")
    }
    if known_evidence:
        unknown = sorted({
            eid
            for claim in claims
            for eid in claim.get("evidence_ids", [])
            if eid not in known_evidence
        })
        if unknown:
            raise QAHardBlockError(
                "claim_matrix.json references evidence IDs that do not exist in this run: "
                + ", ".join(unknown[:12])
                + ". These artifacts likely came from another run. Use "
                f"`report-workflow remap-evidence --from-job <old> --to-job {state.job_id} --write` "
                "or rebuild from this run's evidence_ledger.jsonl."
            )
    validate_evidence_ledger_provenance(evidence_path)
    state.plan["claim_matrix"] = {"claims": claims}
    state.plan["claim_matrix_path"] = write_json_artifact(state, "claim_matrix.json", state.plan["claim_matrix"])
    write_artifact_contract(state.plan["claim_matrix_path"], make_artifact_contract(state))
    return state
