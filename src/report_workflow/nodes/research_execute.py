"""RESEARCH_EXECUTE node — optional external fact-checking via web research backends.

This node reads claims from the factuality report that require external
verification, executes research queries via configured backends (Tavily,
Serper, SerpAPI, BrowserMCP), and writes results to research_results.json.

This node is OPTIONAL and only runs when state.flags["enable_research"] is True.
When no backend is configured, it gracefully falls back to ManualAgentWebBackend
which marks tasks as "pending" without failing the pipeline.
"""
import json
import logging
from pathlib import Path

from ..connectors.research_backends import (
    select_backend,
    get_backend_capability_matrix,
)
from ..state import ReportState, WORKFLOW_RUNS_DIR

logger = logging.getLogger(__name__)


def _build_research_tasks(factuality_report: dict, claim_matrix: dict) -> list[dict]:
    """Build research tasks from claims that need external verification.

    Selects claims that are blocked, or claims with high priority
    that lack sufficient evidence coverage.
    """
    claims_by_id = {
        (c.get("claim_id") or c.get("id", "")): c
        for c in claim_matrix.get("claims", [])
    }
    tasks: list[dict] = []
    seen_claim_ids: set[str] = set()

    for result in factuality_report.get("claims", []):
        claim_id = result.get("claim_id", "")
        status = result.get("status", "")

        # Only research blocked or disputed claims
        if status not in ("blocked", "disputed", "unverified"):
            continue
        if claim_id in seen_claim_ids:
            continue
        seen_claim_ids.add(claim_id)

        claim = claims_by_id.get(claim_id, {})
        claim_text = claim.get("claim_text", "") or claim.get("text", "")
        if not claim_text:
            continue

        # Build a search query from the claim text
        query = claim_text[:200]
        claim_type = claim.get("claim_type", "factual")

        tasks.append({
            "id": f"research_{claim_id}",
            "claim_id": claim_id,
            "query": query,
            "mode": "deep_research" if claim_type == "statistical" else "web_fallback",
            "priority": "high" if status == "blocked" else "medium",
        })

    return tasks


def run_research_execute(state: ReportState) -> ReportState:
    """Execute external research for claims needing verification.

    Skips gracefully if:
      - enable_research flag is not set
      - No factuality report exists
      - No claims need external verification
    """
    if not state.flags.get("enable_research"):
        logger.info("[RESEARCH_EXECUTE] Skipped — enable_research flag not set")
        return state

    run_dir = WORKFLOW_RUNS_DIR / state.job_id

    # Load factuality report
    factuality_path = state.qa.get("factuality_report_path", "")
    if not factuality_path or not Path(factuality_path).exists():
        logger.info("[RESEARCH_EXECUTE] Skipped — no factuality report found")
        return state

    with open(factuality_path, encoding="utf-8") as f:
        factuality_report = json.load(f)

    # Load claim matrix
    claim_matrix_path = run_dir / "claim_matrix.json"
    if not claim_matrix_path.exists():
        logger.info("[RESEARCH_EXECUTE] Skipped — no claim_matrix.json found")
        return state

    with open(claim_matrix_path, encoding="utf-8") as f:
        claim_matrix = json.load(f)

    # Build tasks
    tasks = _build_research_tasks(factuality_report, claim_matrix)
    if not tasks:
        logger.info("[RESEARCH_EXECUTE] No claims require external verification")
        state.research["status"] = "skipped"
        state.research["tasks"] = []
        return state

    logger.info(f"[RESEARCH_EXECUTE] {len(tasks)} claim(s) need external verification")

    # Log backend availability
    matrix = get_backend_capability_matrix()
    configured = [name for name, info in matrix.items() if info.get("configured") and name != "manual_agent_web"]
    if configured:
        logger.info(f"[RESEARCH_EXECUTE] Configured backends: {', '.join(configured)}")
    else:
        logger.warning("[RESEARCH_EXECUTE] No external backends configured — tasks will be marked as pending")

    # Execute tasks
    results: list[dict] = []
    for task in tasks:
        backend = select_backend(task.get("mode", "web_fallback"))
        try:
            result = backend.execute(task)
            results.append(result)
            logger.info(
                f"[RESEARCH_EXECUTE] Task {task['id']}: "
                f"status={result.get('status')}, backend={result.get('backend')}, "
                f"sources={len(result.get('sources', []))}"
            )
        except Exception as exc:
            logger.warning(f"[RESEARCH_EXECUTE] Task {task['id']} failed: {exc}")
            results.append({
                "task_id": task["id"],
                "status": "failed",
                "answer": "",
                "sources": [],
                "confidence": 0.0,
                "backend": backend.name,
                "error": str(exc),
            })

    # Write results
    results_path = run_dir / "research_results.json"
    output = {
        "tasks": tasks,
        "results": results,
        "backend_matrix": matrix,
        "completed_count": sum(1 for r in results if r.get("status") == "completed"),
        "pending_count": sum(1 for r in results if r.get("status") == "pending"),
        "failed_count": sum(1 for r in results if r.get("status") == "failed"),
    }
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    # Update state
    state.research["status"] = "completed" if output["completed_count"] > 0 else "pending"
    state.research["tasks"] = tasks
    state.research["results_path"] = str(results_path)

    logger.info(
        f"[RESEARCH_EXECUTE] Done — {output['completed_count']} completed, "
        f"{output['pending_count']} pending, {output['failed_count']} failed"
    )

    return state
