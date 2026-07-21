"""NOTEBOOK_SYNC node — optional NotebookLM context synchronization.

This node connects to Google NotebookLM to:
  1. Sync notebook context (metadata, sources)
  2. Ask analysis questions about the report's evidence
  3. Record results in state.knowledge_sync

This node is OPTIONAL and only runs when state.flags["enable_notebook_sync"]
is True. When notebooklm-py is not installed, it logs a warning and returns
the state unchanged.
"""
import json
import logging

from ..connectors.notebooklm_connector import (
    notebooklm_available,
    sync_notebook_context,
    ask_analysis_questions,
)
from ..state import ReportState, WORKFLOW_RUNS_DIR

logger = logging.getLogger(__name__)


def run_notebook_sync(state: ReportState) -> ReportState:
    """Sync report context with NotebookLM.

    Skips gracefully if:
      - enable_notebook_sync flag is not set
      - notebooklm-py is not installed
      - No notebook can be found/selected
    """
    if not state.flags.get("enable_notebook_sync"):
        logger.info("[NOTEBOOK_SYNC] Skipped — enable_notebook_sync flag not set")
        return state

    if not notebooklm_available():
        logger.warning(
            "[NOTEBOOK_SYNC] notebooklm-py is not installed — skipping notebook sync. "
            "Install with: pip install notebooklm-py"
        )
        state.knowledge_sync["sync_notes"].append("notebooklm-py not installed, sync skipped")
        return state

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    storage_path = state.spec.get("notebooklm_storage_path")
    notebook_id = state.spec.get("notebooklm_notebook_id")
    topic = state.spec.get("user_prompt", "")[:100]

    # Step 1: Sync notebook context
    logger.info("[NOTEBOOK_SYNC] Syncing notebook context...")
    context = sync_notebook_context(
        storage_path=storage_path,
        notebook_id=notebook_id,
        topic=topic,
    )

    if not context.get("available"):
        error = context.get("error", "Unknown error")
        logger.warning(f"[NOTEBOOK_SYNC] NotebookLM not available: {error}")
        state.knowledge_sync["sync_notes"].append(f"NotebookLM unavailable: {error}")
        state.knowledge_sync["status"] = "skipped"
        return state

    selected = context.get("selected_notebook")
    if not selected:
        logger.warning("[NOTEBOOK_SYNC] No notebook found matching the topic")
        state.knowledge_sync["sync_notes"].append("No matching notebook found")
        state.knowledge_sync["status"] = "skipped"
        return state

    selected_id = selected.get("id", "")
    selected_title = selected.get("title") or selected.get("name", "unknown")
    logger.info(
        f"[NOTEBOOK_SYNC] Selected notebook: {selected_title} ({selected_id}), "
        f"sources: {len(context.get('sources', []))}"
    )

    # Step 2: Ask analysis questions
    logger.info("[NOTEBOOK_SYNC] Asking analysis questions...")
    answers = ask_analysis_questions(
        notebook_id=selected_id,
        storage_path=context["storage_path"],
    )
    completed = sum(1 for a in answers if a.get("status") == "completed")
    logger.info(f"[NOTEBOOK_SYNC] {completed}/{len(answers)} questions answered")

    # Step 3: Record results
    sync_result = {
        "context": context,
        "analysis_answers": answers,
        "notebook_id": selected_id,
        "notebook_title": selected_title,
    }

    results_path = run_dir / "notebook_sync_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(sync_result, f, indent=2, default=str)

    # Update knowledge_sync state
    for answer in answers:
        if answer.get("status") == "completed" and answer.get("answer"):
            state.knowledge_sync["buffer"].append({
                "kind": "analysis_answer",
                "source": "notebooklm",
                "question": answer["question"],
                "content": answer["answer"],
                "notebook_id": selected_id,
            })

    state.knowledge_sync["status"] = "completed" if completed > 0 else "partial"
    state.knowledge_sync["sync_notes"].append(
        f"Synced with notebook '{selected_title}', {completed}/{len(answers)} questions answered"
    )

    logger.info(f"[NOTEBOOK_SYNC] Results saved to {results_path}")
    return state
