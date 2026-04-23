"""REFERENCE_RELEVANCE_GATE - keep only project-bearing references."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState


GENERIC_REFERENCE_PATTERNS = [
    r"\bgradient boosting\b",
    r"\bdeep learning with python\b",
    r"\blabel propagation\b",
    r"\bgeneric\b",
]


def _tokenize_terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text):
        lowered = token.lower()
        if lowered not in {
            "this", "that", "with", "from", "report", "paper", "study",
            "results", "method", "methods", "section", "project",
        }:
            terms.add(lowered)
    return terms


def _project_terms(state: ReportState) -> set[str]:
    identity = state.plan.get("project_identity") or state.spec.get("project_identity") or {}
    terms: set[str] = set()
    for key in ("required_terms", "required_context_terms", "canonical_title_terms"):
        for value in identity.get(key, []) if isinstance(identity, dict) else []:
            terms.update(_tokenize_terms(str(value)))
            terms.add(str(value).lower())
    domain_context = identity.get("domain_context", "") if isinstance(identity, dict) else ""
    if domain_context:
        terms.update(_tokenize_terms(str(domain_context)))
        terms.add(str(domain_context).lower())

    claim_matrix = state.plan.get("claim_matrix") or {}
    for claim in claim_matrix.get("claims", []):
        terms.update(_tokenize_terms(str(claim.get("claim_text", ""))))
        for tag in claim.get("topic_tags", []) or []:
            terms.update(_tokenize_terms(str(tag)))
            terms.add(str(tag).lower())

    terms.update({
        "compiler",
        "compilation",
        "strategyir",
        "strategy",
        "trading",
        "finance",
        "financial",
        "auditability",
        "reproducibility",
        "llm",
        "constrained",
        "grammar",
        "domain-specific",
        "syntax",
    })
    return {term for term in terms if len(term) >= 3}


def _reference_text(ref: dict) -> str:
    return str(ref.get("raw") or ref.get("ref_id") or "")


def _has_relevance(ref_text: str, terms: set[str]) -> bool:
    lowered = ref_text.lower()
    return any(term in lowered for term in terms)


def run_reference_relevance_gate(state: ReportState) -> ReportState:
    """Hard-block generic or non-bearing references for admissions reports."""
    detail = state.spec.get("report_family_detail")
    if detail not in {"admissions_report", "admissions_project_report"}:
        state.runtime["reference_relevance_report_path"] = ""
        return state

    report_path = state.runtime.get("reference_verify_report_path", "")
    if not report_path or not Path(report_path).exists():
        state.runtime["reference_relevance_report_path"] = ""
        return state

    with open(report_path, encoding="utf-8") as f:
        ref_report = json.load(f)

    refs = ref_report.get("references", [])
    terms = _project_terms(state)
    issues: list[str] = []
    checked: list[dict] = []
    publication_grade_count = 0

    for ref in refs:
        ref_text = _reference_text(ref)
        status = ref.get("status", "")
        if status == "excluded":
            checked.append({"ref": ref_text, "status": "excluded", "relevant": False})
            continue
        publication_grade_count += 1
        role_supported = bool(ref.get("reference_role") or ref.get("supports_claim_ids") or ref.get("status") == "project_source")
        matched = sorted(term for term in terms if term in ref_text.lower())[:8]
        generic = any(re.search(pattern, ref_text, re.IGNORECASE) for pattern in GENERIC_REFERENCE_PATTERNS)
        relevant = role_supported or (bool(matched) and not generic)
        checked.append({
            "ref": ref_text,
            "status": status,
            "relevant": relevant,
            "matched_terms": matched,
            "generic": generic,
            "role_supported": role_supported,
        })
        if not relevant:
            issues.append(f"reference is not project-bearing: {ref_text[:120]}")

    if refs and publication_grade_count == 0 and state.spec.get("task_intent") == "new_draft" and detail != "admissions_project_report":
        issues.append("new_draft references are all internal/excluded; bibliography is not publication-bearing")

    report = {
        "job_id": state.job_id,
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "checked": checked,
        "publication_grade_count": publication_grade_count,
    }
    state.runtime["reference_relevance_report_path"] = write_json_artifact(
        state, "reference_relevance_report.json", report
    )
    if issues:
        raise QAHardBlockError("REFERENCE_RELEVANCE_GATE: " + "; ".join(issues[:5]))
    return state
