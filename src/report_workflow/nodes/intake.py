"""INTAKE node - deterministic MVP intake."""
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState


REPORT_FAMILIES = {"academic_report", "work_report", "hybrid_report"}
UNSUPPORTED_DELIVERY_HINTS = (
    "tracked_review",
    "tracked changes",
    "preserve_format",
    "preserve format",
    "keep formatting",
    "retain formatting",
)


def infer_report_family(user_prompt: str) -> str:
    """Infer a conservative report family without calling an LLM."""
    text = user_prompt.lower()
    if "hybrid" in text or ("academic" in text and ("business" in text or "work" in text)):
        return "hybrid_report"
    if any(keyword in text for keyword in ("work report", "business", "executive summary", "recommendation", "client report")):
        return "work_report"
    return "academic_report"


def _enforce_mvp_scope(state: ReportState) -> None:
    task_intent = state.spec.get("task_intent", "new_draft")
    delivery_mode = state.spec.get("delivery_mode", "fresh_doc")
    prompt = state.spec.get("user_prompt", "").lower()

    # revise_existing is now supported; only hard-fail on other delivery modes
    if task_intent not in ("new_draft", "revise_existing"):
        raise QAHardBlockError(
            f"Unsupported task_intent={task_intent!r}; local MVP supports "
            "new_draft and revise_existing."
        )
    if delivery_mode != "fresh_doc" or any(hint in prompt for hint in UNSUPPORTED_DELIVERY_HINTS):
        raise QAHardBlockError(
            "Unsupported MVP delivery mode; local MVP supports only fresh_doc. "
            "preserve_format and tracked_review are future extension paths."
        )


def run_intake(state: ReportState) -> ReportState:
    """T2: INTAKE - populate report_spec deterministically."""
    _enforce_mvp_scope(state)

    override = state.spec.get("report_family_override")
    if override and override not in REPORT_FAMILIES:
        raise QAHardBlockError(f"Unsupported report_family={override!r}")

    # task_intent may already be set by CLI; default to new_draft
    state.spec.setdefault("task_intent", "new_draft")
    state.spec["report_family"] = override or infer_report_family(state.spec.get("user_prompt", ""))
    state.spec.setdefault("delivery_mode", "fresh_doc")
    state.spec.setdefault("audience", "expert")
    state.spec.setdefault("citation_style", "apa")
    state.spec.setdefault("artifact_role_map", {})
    state.spec.setdefault("report_family_detail", "")
    state.spec.setdefault("keywords", [])
    state.spec["report_spec_path"] = write_json_artifact(state, "report_spec.json", state.spec)
    state.update_status("running")
    return state
