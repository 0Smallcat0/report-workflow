"""Workflow node registry and contract snapshot."""
import json
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR


# NOTE: node_registry.py is the authoritative source of record for which nodes exist.
# See run_workflow.py validate_nodes() for the ACTUAL active pipeline.
# Some nodes below are registered here for documentation but are NOT in the critical path:
#   - RESULTS_SANITY_PASS: functionality absorbed into MERGE_DRAFT
#   - MAIN_TEXT_ARTIFACT_FILTER: functionality absorbed into MERGE_DRAFT
#   - CONSISTENCY_CHECK: moved to explicit quality command (check-quality)
#   - GUIDELINE_CHECK: moved to explicit quality command (check-quality)
NODE_REGISTRY = [
    {"id": "INTAKE", "phase": "intake_governance", "status": "mvp", "mvp_enforced": True},
    {"id": "GUIDELINE_SELECT", "phase": "intake_governance", "status": "mvp", "mvp_enforced": False},
    {"id": "BLUEPRINT_PLAN", "phase": "intake_governance", "status": "mvp", "mvp_enforced": True},
    {"id": "CORPUS_BUILD", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "SOURCE_PARSE", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "EVIDENCE_NORMALIZE", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "PROVENANCE_SCORE", "phase": "source_evidence", "status": "mvp_inline", "mvp_enforced": True},
    {"id": "EVIDENCE_STORE", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "AGENT_TASKS", "phase": "agent_handoff", "status": "mvp", "mvp_enforced": True},
    # --- Validate (canonical pipeline) ---
    {"id": "CLAIM_PLAN", "phase": "validate_agent_artifacts", "status": "artifact_contract", "mvp_enforced": True},
    {"id": "OUTLINE_PLAN", "phase": "validate_agent_artifacts", "status": "artifact_contract", "mvp_enforced": True},
    # PAPER_SCOPE_FREEZE: freeze thesis + RQs + contribution framing (addresses scope-drift failure mode)
    {"id": "PAPER_SCOPE_FREEZE", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    {"id": "SECTION_PLAN_FREEZE", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    {"id": "FRONT_MATTER_BUILD", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": False},
    {"id": "SECTION_DRAFT", "phase": "validate_agent_artifacts", "status": "artifact_contract", "mvp_enforced": True},
    {"id": "ABSTRACT_CHECK", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    {"id": "SENTENCE_MAP_BUILD", "phase": "validate_agent_artifacts", "status": "artifact_contract", "mvp_enforced": True},
    # MERGE_DRAFT: canonical single cleaning node (absorbs results_sanity_pass + main_text_artifact_filter)
    {"id": "MERGE_DRAFT", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # SECTION_ROLE_CHECK before CITATION_BIND: catch IMRaD boundary violations before citation stripping
    {"id": "SECTION_ROLE_CHECK", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    {"id": "CITATION_BIND", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # REFERENCE_VERIFY: verify DOI/arXiv resolve (academic mode hard block)
    {"id": "REFERENCE_VERIFY", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    {"id": "FACTUALITY_CHECK", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # FIGURE_QUALITY: consolidated figure quality (absorbs caption_interpreter + figure_contract_check)
    {"id": "FIGURE_QUALITY", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    {"id": "QA_GATE", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # --- Render ---
    {"id": "DOCX_RENDER", "phase": "render_publish", "status": "mvp", "mvp_enforced": True},
    {"id": "FINAL_PUBLISH", "phase": "render_publish", "status": "mvp", "mvp_enforced": True},
    {"id": "ARTIFACTS", "phase": "render_publish", "status": "mvp", "mvp_enforced": True},
    # --- Deprecated / moved to explicit commands ---
    # These exist in codebase but are NOT in the canonical validate_nodes() list:
    {"id": "RESULTS_SANITY_PASS", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into MERGE_DRAFT. Run manually for belt-and-suspenders."},
    {"id": "MAIN_TEXT_ARTIFACT_FILTER", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into MERGE_DRAFT. Run manually for belt-and-suspenders."},
    {"id": "CAPTION_INTERPRETER", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into FIGURE_QUALITY."},
    {"id": "FIGURE_CONTRACT_CHECK", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into FIGURE_QUALITY."},
    {"id": "CONSISTENCY_CHECK", "phase": "validate_agent_artifacts", "status": "explicit_quality_command", "mvp_enforced": False,
     "note": "Run via: report-workflow check-quality --job-id <id>"},
    {"id": "GUIDELINE_CHECK", "phase": "validate_agent_artifacts", "status": "explicit_quality_command", "mvp_enforced": False,
     "note": "Run via: report-workflow check-quality --job-id <id>"},
]


def get_node_registry() -> list[dict]:
    """Return a copy of the canonical workflow node registry."""
    return [dict(node) for node in NODE_REGISTRY]


def run_contract_snapshot(state: ReportState) -> ReportState:
    """Persist a node contract snapshot for this workflow run."""
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "workflow_contract.json"

    snapshot = {
        "version": state.version,
        "node_count": len(NODE_REGISTRY),
        "nodes": get_node_registry(),
        "mvp_completion_rule": "status=completed requires qa_decision=pass and final_docx_path exists",
        "extension_nodes": [
            node["id"] for node in NODE_REGISTRY
            if not node["mvp_enforced"]
        ],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    state.runtime["workflow_contract_path"] = str(path)
    return state
