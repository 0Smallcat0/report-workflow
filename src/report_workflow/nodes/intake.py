"""INTAKE node - deterministic MVP intake."""
from ..errors import QAHardBlockError
from ..profiles import (
    PROFILE_IDS,
    get_profile,
    infer_report_profile,
    normalize_profile_id,
    select_reference_template_mode,
)
from ..runtime_support import write_json_artifact
from ..state import ReportState


REPORT_PROFILES = set(PROFILE_IDS)
UNSUPPORTED_DELIVERY_HINTS = (
    "tracked_review",
    "tracked changes",
    "preserve_format",
    "preserve format",
    "keep formatting",
    "retain formatting",
)


def _enforce_mvp_scope(state: ReportState) -> None:
    task_intent = state.spec.get("task_intent", "new_draft")
    delivery_mode = state.spec.get("delivery_mode", "fresh_doc")
    prompt = state.spec.get("user_prompt", "").lower()

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

    override = normalize_profile_id(state.spec.get("report_profile_override"))
    if override and override not in REPORT_PROFILES:
        raise QAHardBlockError(f"Unsupported report_profile={override!r}")

    state.spec.setdefault("task_intent", "new_draft")
    state.spec["report_profile"] = override or infer_report_profile(state.spec.get("user_prompt", ""))
    profile = get_profile(state.spec["report_profile"])
    state.spec["report_profile_contract"] = profile.to_dict()
    state.spec["reference_template_mode"] = select_reference_template_mode(
        profile.profile_id,
        state.spec.get("user_prompt", ""),
        state.spec.get("reference_template_mode"),
    )
    state.spec.setdefault("delivery_mode", "fresh_doc")
    state.spec.setdefault("audience", "expert")
    state.spec.setdefault("citation_style", "apa")
    state.spec.setdefault("artifact_role_map", {})
    state.spec.setdefault("keywords", [])

    state.spec["report_spec_path"] = write_json_artifact(state, "report_spec.json", state.spec)
    write_json_artifact(state, "report_profile.json", profile.to_dict())
    state.update_status("running")
    return state
