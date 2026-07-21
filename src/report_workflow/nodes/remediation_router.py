"""REMEDIATION_ROUTER - map gate failures to next repair nodes."""
import json

from ..state import ReportState, WORKFLOW_RUNS_DIR


ROUTE_RULES = [
    ("preflight", "PREFLIGHT", "install dependencies and configure required environment variables"),
    ("missing packages", "PREFLIGHT", "install dependencies with pip install -r requirements.txt"),
    ("agent artifact", "AGENT_TASKS", "create the required artifacts listed in agent_tasks"),
    ("agent section draft", "AGENT_TASKS", "create section drafts and sentence_map.jsonl from the task brief"),
    ("agent fallback parser", "SOURCE_PARSE", "provide a supported source type or repair deterministic parsing"),
    ("source_registry", "CORPUS_BUILD", "register source files"),
    ("parsed source", "SOURCE_PARSE", "parse source content"),
    ("source content", "SOURCE_PARSE", "parse source content"),
    ("evidence ledger", "EVIDENCE_NORMALIZE", "normalize evidence"),
    ("claim matrix", "CLAIM_PLAN", "rebuild claims"),
    ("claims missing evidence", "CLAIM_PLAN", "rebuild or seed claims"),
    ("outline", "OUTLINE_PLAN", "rebuild outline"),
    ("section draft", "SECTION_DRAFT", "redraft sections"),
    ("sentence map", "SECTION_DRAFT", "redraft with sentence map"),
    ("merged draft", "MERGE_DRAFT", "merge section drafts"),
    ("placeholder", "SECTION_DRAFT", "replace placeholder draft content"),
    ("citation", "CITATION_BIND", "resolve citations"),
    ("factuality", "CLAIM_PLAN", "revise claims/evidence linkage"),
    ("consistency", "CONSISTENCY_CHECK", "resolve consistency findings"),
    ("style", "STYLE_LINT", "resolve style findings"),
    ("guideline", "GUIDELINE_CHECK", "resolve guideline findings"),
    ("research", "RESEARCH_RETRIEVE", "rerun or repair research retrieval"),
]


def route_reason(reason: str) -> dict:
    lower = reason.lower()
    for needle, node, action in ROUTE_RULES:
        if needle in lower:
            return {
                "reason": reason,
                "target_node": node,
                "recommended_action": action,
            }
    return {
        "reason": reason,
        "target_node": "QA_GATE",
        "recommended_action": "inspect QA failure",
    }


def build_remediation_plan(state: ReportState, hard_fail_reasons: list[str]) -> dict:
    routes = [route_reason(reason) for reason in hard_fail_reasons]
    return {
        "job_id": state.job_id,
        "status": "blocked",
        "routes": routes,
        "target_nodes": sorted({route["target_node"] for route in routes}),
    }


def write_remediation_plan(state: ReportState, hard_fail_reasons: list[str]) -> str:
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "remediation_plan.json"
    plan = build_remediation_plan(state, hard_fail_reasons)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)
    state.governance["remediation_plan_path"] = str(path)
    state.governance["remediation_targets"] = plan["target_nodes"]
    return str(path)
