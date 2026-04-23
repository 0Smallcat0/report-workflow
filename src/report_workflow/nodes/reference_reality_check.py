"""REFERENCE_REALITY_CHECK - summarize reference verification residual risk."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..policies import get_policy
from ..runtime_support import write_json_artifact
from ..state import ReportState


_BOOK_OR_PUBLISHER_RE = re.compile(
    r"\b(Addison[- ]Wesley|Wiley|Manning|Springer|Elsevier|Cambridge|Oxford|MIT Press|"
    r"Princeton|Harvard|University Press|Press)\b|\[[Bb]ook\]|\*[^*]+\*",
    re.IGNORECASE,
)


def _classify_reference(ref: dict) -> tuple[str, str]:
    raw = ref.get("raw") or ref.get("ref_id") or ""
    status = ref.get("status", "")
    errors = "; ".join(ref.get("errors", []))
    checks = ref.get("checks", [])
    has_verified_external_id = any(
        check.get("type") in {"doi", "arxiv"} and check.get("verified")
        for check in checks
    )
    has_failed_external_id = any(
        check.get("type") in {"doi", "arxiv"} and not check.get("verified")
        for check in checks
    )

    if status == "excluded":
        return "excluded_internal_or_non_publication", "Excluded by curation rules"
    if status == "project_source":
        return "project_source_reference", "Internal project source accepted for admissions project reports"
    if has_failed_external_id or status == "failed":
        return "failed_external_verification", errors or "External identifier verification failed"
    if has_verified_external_id or status == "verified":
        return "verified_external_identifier", "DOI or arXiv verification passed"
    if _BOOK_OR_PUBLISHER_RE.search(raw):
        return "publisher_or_book_plausible", "Book/publisher-style reference; no DOI/arXiv required"
    return "needs_human_review", "No DOI/arXiv verification available"


def run_reference_reality_check(state: ReportState) -> ReportState:
    """Create a publication-facing reference verification status report."""
    family = state.spec.get("report_family", "academic_report")
    subtype = state.spec.get("report_family_detail") or None
    policy = get_policy(family, subtype)

    report_path = state.runtime.get("reference_verify_report_path", "")
    if not report_path or not Path(report_path).exists():
        status = "failed" if policy.reference.reality_report_required else "skipped"
        state.runtime["reference_reality_report_path"] = write_json_artifact(
            state,
            "reference_reality_report.json",
            {
                "job_id": state.job_id,
                "status": status,
                "reason": "reference_verify_report.json not found",
                "needs_human_review": [],
            },
        )
        if policy.reference.reality_report_required:
            raise QAHardBlockError("REFERENCE_REALITY_CHECK: reference_verify_report.json not found")
        return state

    with open(report_path, encoding="utf-8") as f:
        ref_report = json.load(f)

    classified = []
    needs_review = []
    failed = []
    for ref in ref_report.get("references", []):
        category, reason = _classify_reference(ref)
        item = {
            "ref_id": ref.get("ref_id", ""),
            "category": category,
            "reason": reason,
        }
        classified.append(item)
        if category == "failed_external_verification":
            failed.append(item)
        elif category == "needs_human_review":
            needs_review.append(item)

    output = {
        "job_id": state.job_id,
        "status": "failed" if failed else ("needs_human_review" if needs_review else "passed"),
        "total_refs": ref_report.get("total_refs", 0),
        "classified_references": classified,
        "failed_external_verification": failed,
        "needs_human_review": needs_review,
    }
    state.runtime["reference_reality_report_path"] = write_json_artifact(
        state, "reference_reality_report.json", output
    )
    if failed:
        raise QAHardBlockError(
            f"REFERENCE_REALITY_CHECK: {len(failed)} reference(s) failed DOI/arXiv verification"
        )
    if needs_review and (state.flags.get("strict_reference_reality_check") or policy.reference.human_review_hard_block):
        raise QAHardBlockError(
            f"REFERENCE_REALITY_CHECK: {len(needs_review)} reference(s) need human verification"
        )
    return state
