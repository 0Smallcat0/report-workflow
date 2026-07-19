"""PROJECT_IDENTITY_GATE - prevent topic-adjacent report drift."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState, WORKFLOW_RUNS_DIR


_SECTION_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _normalize_identity(identity: dict) -> dict:
    normalized = {
        "required_terms": [],
        "required_context_terms": [],
        "forbidden_terms": [],
        "canonical_title_terms": [],
        "domain_context": "",
        "author_metadata": {},
    }
    normalized.update(identity or {})
    for key in (
        "required_terms",
        "required_context_terms",
        "forbidden_terms",
        "canonical_title_terms",
    ):
        value = normalized.get(key) or []
        normalized[key] = [str(item).strip() for item in value if str(item).strip()]
    normalized["domain_context"] = str(normalized.get("domain_context") or "").strip()
    if not isinstance(normalized.get("author_metadata"), dict):
        normalized["author_metadata"] = {}
    return normalized


def _load_project_identity(state: ReportState) -> dict | None:
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    file_identity: dict = {}
    identity_path = run_dir / "project_identity.json"
    if identity_path.exists():
        with open(identity_path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            file_identity = loaded

    spec_identity = state.spec.get("project_identity")
    if isinstance(spec_identity, dict) and spec_identity:
        merged = {**file_identity, **spec_identity}
        identity = _normalize_identity(merged)
    elif file_identity:
        identity = _normalize_identity(file_identity)
    else:
        return None

    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(json.dumps(identity, indent=2), encoding="utf-8")
    state.plan["project_identity"] = identity
    state.plan["project_identity_path"] = str(identity_path)
    return identity


def _term_present(text: str, term: str) -> bool:
    if not term:
        return True
    flags = re.IGNORECASE
    if re.fullmatch(r"[A-Za-z0-9_]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text, flags))
    parts = [part for part in re.split(r"[\s-]+", term.strip()) if part]
    if len(parts) > 1 and all(re.fullmatch(r"[A-Za-z0-9_]+", part) for part in parts):
        pattern = r"\b" + r"[\s-]+".join(re.escape(part) for part in parts) + r"\b"
        return bool(re.search(pattern, text, flags))
    return bool(re.search(re.escape(term), text, flags))


def _section_content(markdown: str, wanted: str) -> str:
    matches = list(_SECTION_RE.finditer(markdown))
    for index, match in enumerate(matches):
        heading = match.group(1).strip().lower()
        heading = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", heading)
        if heading == wanted.lower():
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            return markdown[start:end].strip()
    return ""


def _identity_hits(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if _term_present(text, term)]


def _domain_context_present(text: str, domain_context: str) -> bool:
    """Accept exact context or distributed key-term coverage.

    Admissions project identities often use descriptive context phrases such as
    "Taiwan equities and graduate admissions project introduction". Requiring
    that exact phrase forces awkward meta prose into the final document, even
    when all meaningful context terms are already present.
    """
    if not domain_context:
        return True
    if _term_present(text, domain_context):
        return True

    tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9_]+", domain_context.lower())
        if token not in {"and", "or", "the", "a", "an", "for", "of", "to"}
    ]
    if not tokens:
        return False
    hits = sum(1 for token in tokens if _term_present(text, token))
    return hits >= max(2, len(tokens) - 1)


def _validate_author_metadata(front_matter: dict, author_metadata: dict) -> list[str]:
    issues: list[str] = []
    for field, expected in author_metadata.items():
        if not expected:
            continue
        actual = str(front_matter.get(field, "")).strip()
        if str(expected).strip() not in actual:
            issues.append(f"front matter {field!r} does not contain expected value {expected!r}")
    return issues


def run_project_identity_gate(state: ReportState) -> ReportState:
    """Hard-block final drafts that drift away from the project identity."""
    identity = _load_project_identity(state)
    if not identity:
        state.runtime["project_identity_report_path"] = ""
        return state

    draft_path = state.drafts.get("merged_draft_md") or state.drafts.get("publication_style_draft")
    markdown = Path(draft_path).read_text(encoding="utf-8") if draft_path and Path(draft_path).exists() else ""
    front_matter = state.plan.get("front_matter") or {}
    outline = state.plan.get("outline") if isinstance(state.plan.get("outline"), dict) else {}
    title = str(front_matter.get("title") or "")
    thesis = str(
        state.plan.get("thesis_statement")
        or outline.get("thesis_statement")
        or outline.get("primary_contribution")
        or state.plan.get("primary_contribution")
        or ""
    )
    abstract = _section_content(markdown, "abstract")
    introduction = _section_content(markdown, "introduction")
    full_text = "\n".join([title, thesis, abstract, introduction, markdown])

    required_terms = identity["required_terms"]
    context_terms = identity["required_context_terms"]
    all_identity_terms = required_terms + context_terms
    issues: list[str] = []

    missing_required = [term for term in required_terms if not _term_present(full_text, term)]
    if missing_required:
        issues.append("required project identity terms missing: " + ", ".join(missing_required))

    domain_context = identity.get("domain_context", "")
    if domain_context and not _domain_context_present(full_text, domain_context):
        issues.append(f"domain context missing: {domain_context}")

    forbidden_found = [term for term in identity["forbidden_terms"] if _term_present(full_text, term)]
    if forbidden_found:
        issues.append("forbidden drift/template terms present: " + ", ".join(forbidden_found))

    title_terms = identity["canonical_title_terms"] or required_terms
    if title_terms and not _identity_hits(title, title_terms):
        issues.append("title does not contain any canonical project identity term")

    if required_terms and len(_identity_hits(thesis, required_terms)) < min(2, len(required_terms)):
        issues.append("frozen thesis/primary contribution does not retain enough required identity terms")

    for label, text in (("abstract", abstract), ("introduction", introduction)):
        if not text:
            issues.append(f"{label} section not found for project identity check")
            continue
        if all_identity_terms and len(_identity_hits(text, all_identity_terms)) < 2:
            issues.append(f"{label} does not retain enough project identity terms")

    issues.extend(_validate_author_metadata(front_matter, identity.get("author_metadata") or {}))

    report = {
        "job_id": state.job_id,
        "status": "passed" if not issues else "failed",
        "identity": identity,
        "issues": issues,
        "hits": {
            "title": _identity_hits(title, title_terms),
            "thesis": _identity_hits(thesis, required_terms),
            "abstract": _identity_hits(abstract, all_identity_terms),
            "introduction": _identity_hits(introduction, all_identity_terms),
        },
    }
    state.runtime["project_identity_report_path"] = write_json_artifact(
        state, "project_identity_report.json", report
    )
    if issues:
        raise QAHardBlockError("PROJECT_IDENTITY_GATE: " + "; ".join(issues))
    return state
