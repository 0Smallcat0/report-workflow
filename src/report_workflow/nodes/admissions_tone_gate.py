"""ADMISSIONS_TONE_GATE - admissions-facing but scholarly tone checks."""
from __future__ import annotations

import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState


META_READER_PATTERNS = [
    r"\bFor an admissions committee\b",
    r"\bfor graduate admissions purposes\b",
    r"\bthis report is suitable for\b",
    r"\bfor admissions committee review\b",
]

def _section_content(markdown: str, wanted: str) -> str:
    heading_re = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(markdown))
    for index, match in enumerate(matches):
        heading = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", match.group(1).strip().lower())
        if heading == wanted.lower():
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            return markdown[start:end].strip()
    return ""


def _identity_terms(state: ReportState) -> list[str]:
    identity = state.plan.get("project_identity") or state.spec.get("project_identity") or {}
    if not isinstance(identity, dict):
        return []
    terms: list[str] = []
    for key in ("required_terms", "required_context_terms", "canonical_title_terms"):
        for value in identity.get(key, []) or []:
            term = str(value).strip()
            if term:
                terms.append(term)
    domain_context = str(identity.get("domain_context") or "").strip()
    if domain_context:
        terms.extend(
            token
            for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", domain_context)
            if token.lower() not in {"this", "that", "with", "from", "report", "project"}
        )
    return list(dict.fromkeys(terms))


def _term_present(text: str, term: str) -> bool:
    if not term:
        return True
    if re.fullmatch(r"[A-Za-z0-9_]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE))
    parts = [part for part in re.split(r"[\s-]+", term.strip()) if part]
    if len(parts) > 1 and all(re.fullmatch(r"[A-Za-z0-9_]+", part) for part in parts):
        pattern = r"\b" + r"[\s-]+".join(re.escape(part) for part in parts) + r"\b"
        return bool(re.search(pattern, text, re.IGNORECASE))
    return bool(re.search(re.escape(term), text, re.IGNORECASE))


def run_admissions_tone_gate(state: ReportState) -> ReportState:
    """Hard-block meta admissions prose and generic conclusions."""
    if state.spec.get("report_profile") != "admissions_report":
        state.runtime["admissions_tone_report_path"] = ""
        return state

    draft_path = (
        state.drafts.get("publication_style_draft")
        or state.drafts.get("merged_draft_cited_md")
        or state.drafts.get("merged_draft_md")
    )
    if not draft_path or not Path(draft_path).exists():
        state.runtime["admissions_tone_report_path"] = ""
        return state

    markdown = Path(draft_path).read_text(encoding="utf-8")
    issues: list[str] = []

    for pattern in META_READER_PATTERNS:
        if re.search(pattern, markdown, re.IGNORECASE):
            issues.append(f"meta-reader phrase found: {pattern}")

    conclusion = _section_content(markdown, "conclusion")
    if conclusion:
        repeated = re.findall(r"\bThis project demonstrates\b", conclusion, re.IGNORECASE)
        if len(repeated) > 1:
            issues.append("conclusion repeats 'This project demonstrates' without adding density")
        if state.spec.get("task_intent") == "new_draft":
            identity_terms = _identity_terms(state)
            if identity_terms and not any(_term_present(conclusion, term) for term in identity_terms):
                issues.append(
                    "new_draft conclusion does not retain project identity terms"
                )

    report = {
        "job_id": state.job_id,
        "status": "passed" if not issues else "failed",
        "issues": issues,
    }
    state.runtime["admissions_tone_report_path"] = write_json_artifact(
        state, "admissions_tone_report.json", report
    )
    if issues:
        raise QAHardBlockError("ADMISSIONS_TONE_GATE: " + "; ".join(issues))
    return state
