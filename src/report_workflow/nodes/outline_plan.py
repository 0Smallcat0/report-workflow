"""OUTLINE_PLAN node - load and validate agent-produced outline.json."""
import json
from pathlib import Path

from ..errors import AgentWorkRequired, QAHardBlockError
from ..runtime_support import run_dir_for, write_json_artifact
from ..state import ReportState
from ..artifact_contract import make_artifact_contract, validate_artifact_contract, write_artifact_contract
from .agent_tasks import missing_agent_artifacts, write_agent_task_briefs
from .section_contract import validate_required_outline_sections


def _outline_path(state: ReportState) -> Path:
    return run_dir_for(state) / "outline.json"


def _load_outline(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise QAHardBlockError(f"Malformed outline.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise QAHardBlockError("outline.json must contain a JSON object")
    return payload


def run_outline_plan(state: ReportState) -> ReportState:
    """T9: OUTLINE_PLAN - load agent-authored outline."""
    path = _outline_path(state)
    if not path.exists():
        write_agent_task_briefs(state)
        missing = missing_agent_artifacts(state, str(path))
        state.update_status("awaiting_agent_artifacts")
        raise AgentWorkRequired(f"Agent artifact required: {path}", missing)

    result = _load_outline(path)
    validate_artifact_contract(state, path, allow_missing=True)
    sections = result.get("sections", {})
    if not isinstance(sections, dict) or not sections:
        raise QAHardBlockError("outline.json must contain a non-empty sections object")

    blueprint_sections = set((state.plan.get("blueprint") or {}).get("sections", {}).keys())
    allowed_sections = set(blueprint_sections)
    revise_mode = state.spec.get("task_intent") == "revise_existing"
    if revise_mode:
        # In revise_existing the document's shape is the *base document's*,
        # not the new-draft blueprint's: its parsed section ids are the valid
        # outline targets. Validating a revision outline against the blueprint
        # rejected every real base document whose headings differ from the
        # blueprint (any Chinese document, any custom structure).
        base_sections_path = run_dir_for(state) / "base_document_sections.json"
        if base_sections_path.exists():
            try:
                with open(base_sections_path, encoding="utf-8") as f:
                    base_sections = json.load(f)
                if isinstance(base_sections, dict):
                    allowed_sections.update(base_sections.keys())
            except json.JSONDecodeError:
                pass
    unknown_sections = sorted(section_id for section_id in sections if allowed_sections and section_id not in allowed_sections)
    if unknown_sections:
        raise QAHardBlockError(f"Outline references unknown sections: {', '.join(unknown_sections)}")
    if not revise_mode:
        # Blueprint-required sections apply to new drafts only; a revision
        # outline mirrors whatever sections the base document actually has.
        validate_required_outline_sections(state.plan.get("blueprint") or {}, sections)

    assigned_claims = set()
    for section_id, section in sections.items():
        if not isinstance(section, dict):
            raise QAHardBlockError(f"Outline section {section_id} must be an object")
        section.setdefault("section_id", section_id)
        claim_ids = section.get("claim_ids", [])
        if not isinstance(claim_ids, list):
            raise QAHardBlockError(f"Outline section {section_id} claim_ids must be a list")
        assigned_claims.update(claim_ids)

    claim_ids = {claim.get("claim_id") for claim in state.plan.get("claim_matrix", {}).get("claims", [])}
    missing = sorted(claim_id for claim_id in claim_ids if claim_id and claim_id not in assigned_claims)
    if missing:
        raise QAHardBlockError(f"Outline did not assign claims: {', '.join(missing)}")

    unknown_claims = sorted(claim_id for claim_id in assigned_claims if claim_id not in claim_ids)
    if unknown_claims:
        raise QAHardBlockError(f"Outline references unknown claims: {', '.join(unknown_claims)}")

    state.plan["outline"] = result
    state.plan["outline_path"] = write_json_artifact(state, "outline.json", result)
    write_artifact_contract(state.plan["outline_path"], make_artifact_contract(state))
    return state
