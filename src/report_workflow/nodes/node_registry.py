"""Workflow node registry and contract snapshot."""
import json
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR


# NOTE: node_registry.py is the authoritative source of record for which nodes exist.
# See run_workflow.py validate_nodes() for the ACTUAL active pipeline (11 nodes after consolidation).
# Consolidated nodes (17 → 11) per §6.2 academic-report-simplify-retrospective.
NODE_REGISTRY = [
    # --- Prepare (9 nodes) ---
    {"id": "INTAKE", "phase": "intake_governance", "status": "mvp", "mvp_enforced": True},
    {"id": "GUIDELINE_SELECT", "phase": "intake_governance", "status": "mvp", "mvp_enforced": False},
    {"id": "BLUEPRINT_PLAN", "phase": "intake_governance", "status": "mvp", "mvp_enforced": True},
    {"id": "CORPUS_BUILD", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "SOURCE_PARSE", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "EVIDENCE_NORMALIZE", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "PROVENANCE_SCORE", "phase": "source_evidence", "status": "mvp_inline", "mvp_enforced": True},
    {"id": "EVIDENCE_STORE", "phase": "source_evidence", "status": "mvp", "mvp_enforced": True},
    {"id": "AGENT_TASKS", "phase": "agent_handoff", "status": "mvp", "mvp_enforced": True},
    # --- Validate (11 nodes, post-consolidation) ---
    # AGENT_ARTIFACT_INTAKE: CLAIM_PLAN + OUTLINE_PLAN + SECTION_DRAFT combined
    {"id": "AGENT_ARTIFACT_INTAKE", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True,
     "note": "Consolidates: CLAIM_PLAN, OUTLINE_PLAN, SECTION_DRAFT"},
    # PLAN_FREEZE: PAPER_SCOPE_FREEZE + SECTION_PLAN_FREEZE combined
    {"id": "PLAN_FREEZE", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True,
     "note": "Consolidates: PAPER_SCOPE_FREEZE, SECTION_PLAN_FREEZE"},
    # DOC_METADATA_GATE: FRONT_MATTER_BUILD + ABSTRACT_CHECK combined
    {"id": "DOC_METADATA_GATE", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True,
     "note": "Consolidates: FRONT_MATTER_BUILD, ABSTRACT_CHECK"},
    {"id": "METHODS_PROTOCOL_BUILD", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    {"id": "FIGURE_BUILD", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # DRAFT_ASSEMBLY: REVISION_APPLY + MERGE_DRAFT combined
    {"id": "DRAFT_ASSEMBLY", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True,
     "note": "Consolidates: REVISION_APPLY, MERGE_DRAFT (which absorbs results_sanity_pass + main_text_artifact_filter)"},
    {"id": "SECTION_ROLE_CHECK", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # CITATION_LAYER: CITATION_BIND + REFERENCE_VERIFY combined
    {"id": "CITATION_LAYER", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True,
     "note": "Consolidates: CITATION_BIND, REFERENCE_VERIFY"},
    {"id": "FACTUALITY_CHECK", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # FIGURE_QUALITY: absorbs caption_interpreter + figure_contract_check
    {"id": "FIGURE_QUALITY", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True,
     "note": "Consolidates: caption_interpreter, figure_contract_check"},
    {"id": "QA_GATE", "phase": "validate_agent_artifacts", "status": "mvp", "mvp_enforced": True},
    # --- Render (6 nodes) ---
    {"id": "DOCX_RENDER", "phase": "render_publish", "status": "mvp", "mvp_enforced": True},
    {"id": "FINAL_PUBLISH", "phase": "render_publish", "status": "mvp", "mvp_enforced": True},
    {"id": "ARTIFACTS", "phase": "render_publish", "status": "mvp", "mvp_enforced": True},
    # --- Deprecated / explicit quality commands ---
    {"id": "RESULTS_SANITY_PASS", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "DELETED from disk. Functionality absorbed into DRAFT_ASSEMBLY (via MERGE_DRAFT)."},
    {"id": "MAIN_TEXT_ARTIFACT_FILTER", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "DELETED from disk. Functionality absorbed into DRAFT_ASSEMBLY (via MERGE_DRAFT)."},
    {"id": "CAPTION_INTERPRETER", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "DELETED from disk. Functionality absorbed into FIGURE_QUALITY."},
    {"id": "FIGURE_CONTRACT_CHECK", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "DELETED from disk. Functionality absorbed into FIGURE_QUALITY."},
    # Individual constituent nodes — deprecated, replaced by consolidated wrappers above
    {"id": "CLAIM_PLAN", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into AGENT_ARTIFACT_INTAKE."},
    {"id": "OUTLINE_PLAN", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into AGENT_ARTIFACT_INTAKE."},
    {"id": "PAPER_SCOPE_FREEZE", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into PLAN_FREEZE."},
    {"id": "SECTION_PLAN_FREEZE", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into PLAN_FREEZE."},
    {"id": "FRONT_MATTER_BUILD", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into DOC_METADATA_GATE."},
    {"id": "SECTION_DRAFT", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into AGENT_ARTIFACT_INTAKE."},
    {"id": "ABSTRACT_CHECK", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into DOC_METADATA_GATE."},
    {"id": "REVISION_APPLY", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into DRAFT_ASSEMBLY."},
    {"id": "MERGE_DRAFT", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into DRAFT_ASSEMBLY. File kept for belt-and-suspenders imports."},
    {"id": "CITATION_BIND", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into CITATION_LAYER."},
    {"id": "REFERENCE_VERIFY", "phase": "validate_agent_artifacts", "status": "deprecated", "mvp_enforced": False,
     "note": "Absorbed into CITATION_LAYER."},
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
