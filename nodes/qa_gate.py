"""QA_GATE node - pass/fail decision based on factuality and citation reports."""
import json
import logging
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR

logger = logging.getLogger(__name__)


class QAHardBlockError(Exception):
    """Raised when QA finds a hard blocker."""
    pass


def run_qa_gate(state: ReportState) -> ReportState:
    """T14: QA_GATE - make pass/fail decision based on reports."""
    factuality_path = state.qa.get("factuality_report_path")

    # Default decision
    qa_decision = "pass"
    waiver_records = []

    # Load factuality report
    if factuality_path and Path(factuality_path).exists():
        try:
            with open(factuality_path) as f:
                factuality_report = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.exception(f"[QA_GATE] failed to load factuality report: {exc}")
            factuality_report = {}

        blocked_count = factuality_report.get("blocked_count", 0)
        disputed_count = factuality_report.get("disputed_count", 0)

        if blocked_count > 0:
            qa_decision = "hard_fail"
        elif disputed_count > 0:
            qa_decision = "hard_fail"  # disputed = unverified inference, cannot waive
    else:
        disputed_count = 0

    # Check citation audit
    citation_audit = state.citations.get("citation_audit", [])
    unresolved = [c for c in citation_audit if not c.get("resolved", False)]

    if unresolved:
        qa_decision = "hard_fail"

    # Soft blockers (Phase 2 CONSISTENCY_CHECK, etc.) - none in Phase 1

    # Write waiver records
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    waiver_path = run_dir / "waiver_records.json"
    with open(waiver_path, "w") as f:
        json.dump(waiver_records, f, indent=2)
    
    state.qa["qa_decision"] = qa_decision
    state.qa["waiver_records"] = waiver_records
    
    # If hard fail, update status
    if qa_decision == "hard_fail":
        state.update_status("failed")
    
    return state
