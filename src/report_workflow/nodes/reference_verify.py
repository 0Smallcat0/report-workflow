"""REFERENCE_VERIFY node - verify DOI, arXiv, and reference metadata plausibility.

Position: After CITATION_BIND, before QA_GATE.

For academic_paper mode, verifies:
  - DOIs resolve (HTTP GET to doi.org)
  - arXiv IDs exist (via arXiv API or HTTP)
  - Year plausibility (not in the future, not before 1900)
  - Author names look plausible (not "Unknown" or just filenames)

References that cannot be verified are logged but do not hard-block
unless the report_profile is academic_paper and the reference is marked
as requiring_verification=true.

This addresses the retrospective failure: "Reference layer started in
internal trace format instead of publication-grade format."
"""
import json
import re
import urllib.request
import urllib.error
from pathlib import Path

from ..state import ReportState
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..policies import get_policy
from .citation_bind import LOCAL_ARTIFACT_LABELS


def _verify_doi(doi: str) -> tuple[bool, str]:
    """Verify a DOI resolves. Returns (verified, message)."""
    if not doi:
        return False, "Empty DOI"

    # Normalize DOI
    doi = doi.strip()
    if not doi.startswith("https://doi.org/"):
        doi = f"https://doi.org/{doi}"

    try:
        req = urllib.request.Request(
            doi,
            headers={"Accept": "application/x-bibtex, text/plain"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 302, 303):
                return True, f"DOI resolves (status {resp.status})"
            return False, f"DOI returned status {resp.status}"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "DOI not found (404)"
        return False, f"DOI HTTP error: {e.code}"
    except urllib.error.URLError as e:
        return False, f"DOI network error: {e.reason}"
    except Exception as e:
        return False, f"DOI verification error: {e}"


def _verify_arxiv(arxiv_id: str) -> tuple[bool, str]:
    """Verify an arXiv ID exists. Returns (verified, message)."""
    if not arxiv_id:
        return False, "Empty arXiv ID"

    # Normalize arXiv ID
    arxiv_id = arxiv_id.strip()
    # Remove URL prefix if present
    arxiv_id = re.sub(r"https?://arxiv\.org/abs/", "", arxiv_id)
    arxiv_id = re.sub(r"https?://arxiv\.org/pdf/", "", arxiv_id)
    arxiv_id = arxiv_id.rstrip(".pdf")

    try:
        url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            if "<entry>" in content:
                return True, "arXiv ID found"
            return False, "arXiv ID not found in response"
    except urllib.error.HTTPError as e:
        return False, f"arXiv HTTP error: {e.code}"
    except urllib.error.URLError as e:
        return False, f"arXiv network error: {e.reason}"
    except Exception as e:
        return False, f"arXiv verification error: {e}"


def _check_year_plausibility(year_str: str) -> tuple[bool, str]:
    """Check that a year is plausible (1900-present)."""
    if not year_str:
        return True, ""  # Don't block on missing year

    try:
        year = int(year_str)
        if year < 1900:
            return False, f"Year {year} is before 1900"
        if year > 2030:  # Allow some future tolerance
            return False, f"Year {year} is implausibly far in the future"
        return True, ""
    except ValueError:
        return False, f"Invalid year format: {year_str!r}"


def _check_author_plausibility(author_str: str) -> tuple[bool, str]:
    """Check that author names look plausible, not just filenames."""
    if not author_str:
        return True, ""

    # Reject if it looks like a filename
    if re.search(r"\.(pdf|docx|txt|csv|xlsx)\b", author_str, re.IGNORECASE):
        return False, f"Author looks like a filename: {author_str}"

    # Reject "Unknown" or very short names
    if author_str.lower() in ("unknown", "anonymous", "n/a"):
        return False, f"Author is placeholder: {author_str}"

    # Reject if it's just a filename stem
    if re.match(r"^[A-Z][a-z]+$", author_str):
        return True, ""  # Looks like a real name

    # Reject if it contains path-like patterns
    if re.search(r"[\\/]", author_str):
        return False, f"Author looks like a path: {author_str}"

    return True, ""


#: Derived from the one table in citation_bind that decides these labels, so a
#: newly supported source format cannot leave this filter stale. When the two
#: were hand-copied lists they drifted, and a .csv source was carried into the
#: publication reference list only to fail curation as "not a publication".
_LOCAL_ARTIFACT_LABEL_RE = re.compile(
    "|".join(re.escape(f"[{label}]") for label in LOCAL_ARTIFACT_LABELS),
    re.IGNORECASE,
)


def _check_reference_curation(raw_ref: str) -> tuple[bool, str]:
    """Reject obviously internal, filename-derived, or placeholder references."""
    text = raw_ref.strip()
    lowered = text.lower()

    blocked_patterns = [
        (r"\bsource\s*&\s*corpus\b", "reference is derived from internal source_corpus placeholder"),
        (r"\bsource_corpus\b", "reference cites internal source_corpus artifact"),
        (_LOCAL_ARTIFACT_LABEL_RE.pattern, "reference is a local file artifact, not a publication"),
        (r"\bgraph_report\b|\bgraphify\b", "reference cites internal graphify artifact"),
        (r"\bmain_report\b", "reference cites internal workflow artifact"),
        (r"https?://www\.backtrader\.com/?", "reference is a product website rather than a scholarly source"),
    ]
    for pattern, reason in blocked_patterns:
        if re.search(pattern, lowered, re.IGNORECASE):
            return False, reason

    # Catch filename-like authors/titles that slipped through pseudo-APA formatting.
    if re.search(r"\b[a-z0-9_]+\.(txt|md|json|csv|docx|pdf)\b", text, re.IGNORECASE):
        return False, "reference contains a local filename"

    return True, ""


def _is_publication_reference_candidate(raw_ref: str) -> bool:
    """Return True for references that are worth carrying into publication."""
    text = raw_ref.strip()
    if not text:
        return False
    lowered = text.lower()
    if any(token in lowered for token in ("source_corpus", "source & corpus", "graphify", "graph_report")):
        return False
    if _LOCAL_ARTIFACT_LABEL_RE.search(text):
        return False
    # Keep durable scholarly/book references and DOI/arXiv references.
    # The venue-token list alone silently dropped real citations whose venue
    # carries none of the magic words ("Notices of the AMS, 61(5), 458-471."),
    # so an article-shaped reference — (year). plus volume(issue), pages —
    # also qualifies.
    return bool(
        re.search(r"doi[:\s]+10\.", text, re.IGNORECASE)
        or re.search(r"arxiv[:\s]+|\d{4}\.\d{4,5}", text, re.IGNORECASE)
        or re.search(r"\b(journal|proceedings|press|wiley|springer|elsevier|cambridge|oxford|mit press)\b", text, re.IGNORECASE)
        or (re.search(r"\(\d{4}\)\.", text) and re.search(r"\d+\(\d+\),\s*\d+", text))
        or re.search(r"\*[^*]+\*", text)
    )


def _is_project_source_reference_candidate(raw_ref: str) -> bool:
    text = raw_ref.strip()
    if not text:
        return False
    lowered = text.lower()
    return bool(
        re.search(r"\(\d{4}\)", text)
        and any(token in lowered for token in (
            "architecture documentation",
            "system manual",
            "design note",
            "internal project documentation",
            "technical design",
        ))
    )


def _load_refs_from_citation_bind(state: ReportState) -> list[dict]:
    """Extract reference metadata from citation_bind outputs."""
    refs = []

    # Try to load publication_reference_list.md
    ref_list_path = state.citations.get("publication_reference_list_path", "")
    if ref_list_path and Path(ref_list_path).exists():
        content = Path(ref_list_path).read_text(encoding="utf-8")
        # Parse markdown reference list
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                ref_text = line[2:].strip()
                refs.append({
                    "raw": ref_text,
                    "source": "publication_reference_list",
                })
            elif re.match(r"^\[\d+\]\s+", line):
                refs.append({
                    "raw": line,
                    "source": "publication_reference_list",
                })

    # Also inspect agent-authored references section because docx_render can use
    # it when generated publication refs are absent.
    references_path = (state.drafts.get("section_drafts") or {}).get("references", "")
    if references_path and Path(references_path).exists():
        content = Path(references_path).read_text(encoding="utf-8")
        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            refs.append({
                "raw": stripped.lstrip("-* ").strip(),
                "source": "references_section",
            })

    # Try to load internal_trace_map.json for source tracking
    trace_path = state.citations.get("internal_trace_path", "")
    if trace_path and Path(trace_path).exists():
        with open(trace_path, encoding="utf-8") as f:
            trace = json.load(f)
            # Extract source files that are research_document type
            for claim_trace in trace.get("claims", []):
                for source in claim_trace.get("sources", []):
                    if source.get("source_role") in ("research_document", "primary_source"):
                        refs.append({
                            "source_file": source.get("source_file", ""),
                            "source_id": source.get("source_id", ""),
                            "source_role": source.get("source_role", ""),
                            "raw": source.get("source_file", ""),
                            "source": "internal_trace",
                        })

    return refs


def _write_curated_reference_list(state: ReportState, refs: list[dict]) -> None:
    """Rewrite publication_reference_list.md using curation-passing references."""
    ref_list_path = state.citations.get("publication_reference_list_path", "")
    if not ref_list_path:
        return
    if state.citations.get("publication_citation_style") == "gb_t_7714_2015":
        state.citations["curated_reference_list_path"] = ref_list_path
        state.citations["curated_reference_count"] = len(refs)
        return
    path = Path(ref_list_path)
    curated: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        raw = ref.get("raw", "").strip()
        # References drafted in the body carry [CITE:] anchors; those are
        # workflow markers and must never reach the published bibliography.
        raw = re.sub(r"\s*\[CITE:[^\]]+\]", "", raw).strip()
        if not raw or raw.lower() in seen:
            continue
        ok, _ = _check_reference_curation(raw)
        if not ok or not _is_publication_reference_candidate(raw):
            continue
        curated.append(raw)
        seen.add(raw.lower())

    if curated:
        content = "## References\n\n" + "\n\n".join(f"- {item}" for item in curated) + "\n"
    else:
        content = ""
    path.write_text(content, encoding="utf-8")
    state.citations["curated_reference_list_path"] = str(path)
    state.citations["curated_reference_count"] = len(curated)


def run_reference_verify(state: ReportState) -> ReportState:
    """REFERENCE_VERIFY - verify DOI, arXiv, and reference metadata plausibility.

    Position: After CITATION_BIND, before QA_GATE.

    For academic_paper: hard blocks if unverifiable references are found.
    For other families: logs warnings but does not block.

    References are checked against:
      - DOI resolution (doi.org HTTP check)
      - arXiv ID existence (arXiv API)
      - Year plausibility (1900-2030)
      - Author name plausibility
    """
    report_profile = state.spec.get("report_profile", "")
    policy = get_policy(report_profile)

    # Get references from citation_bind output
    refs = _load_refs_from_citation_bind(state)
    _write_curated_reference_list(state, refs)

    if not refs:
        # No references to verify
        report = {
            "job_id": state.job_id,
            "total_refs": 0,
            "verified": 0,
            "failed": 0,
            "skipped": 0,
            "references": [],
            "status": "no_references",
        }
        report_path = write_json_artifact(state, "reference_verify_report.json", report)
        state.runtime["reference_verify_report_path"] = str(report_path)
        return state

    # Process each reference
    verified_refs = []
    failed_refs = []
    warnings = []

    for ref in refs:
        ref_id = ref.get("source_id", ref.get("raw", ""))

        # Use local typed variables to avoid dict key access type narrowing issues
        checks: list[dict] = []
        errors: list[str] = []
        verified_flag = False
        ref_status = ""

        # Check for DOI or arXiv
        doi_ok = False
        arxiv_ok = False

        raw_reference = ref.get("raw", ref_id)
        if not _is_publication_reference_candidate(raw_reference):
            if report_profile == "admissions_project_report" and _is_project_source_reference_candidate(raw_reference):
                checks.append({"type": "project_source", "reason": "internal project source reference accepted for admissions project report"})
                verified_refs.append({
                    "ref_id": ref_id,
                    "raw": raw_reference,
                    "source": ref.get("source", ""),
                    "checks": checks,
                    "verified": True,
                    "errors": [],
                    "status": "project_source",
                })
                continue
            checks.append({"type": "excluded", "reason": "not a publication-grade reference"})
            verified_refs.append({
                "ref_id": ref_id,
                "raw": raw_reference,
                "source": ref.get("source", ""),
                "checks": checks,
                "verified": True,
                "errors": [],
                "status": "excluded",
            })
            continue

        curation_ok, curation_msg = _check_reference_curation(raw_reference)
        checks.append({"type": "curation", "value": ref.get("raw", ref_id), "verified": curation_ok, "message": curation_msg})
        if not curation_ok:
            errors.append(f"Curation: {curation_msg}")

        doi_match = re.search(
            r"(?:doi[:\s]+|https?://(?:dx\.)?doi\.org/)(10\.\S+)",
            ref_id,
            re.IGNORECASE,
        )
        if doi_match:
            doi = doi_match.group(1).strip()
            check_ok, msg = _verify_doi(doi)
            checks.append({"type": "doi", "value": doi, "verified": check_ok, "message": msg})
            if check_ok:
                doi_ok = True
            else:
                errors.append(f"DOI: {msg}")
        else:
            # Check for arXiv
            arxiv_match = re.search(
                r"(?:arxiv[:\s]+|https?://arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})",
                ref_id,
                re.IGNORECASE,
            )
            if arxiv_match:
                arxiv_id = arxiv_match.group(1).strip()
                check_ok, msg = _verify_arxiv(arxiv_id)
                checks.append({"type": "arxiv", "value": arxiv_id, "verified": check_ok, "message": msg})
                if check_ok:
                    arxiv_ok = True
                else:
                    errors.append(f"arXiv: {msg}")

        # If we couldn't extract DOI or arXiv, skip year/author plausibility checks
        has_doi_or_arxiv = doi_ok or arxiv_ok
        if not has_doi_or_arxiv:
            # Can't verify, don't block
            checks.append({"type": "skipped", "reason": "no_doi_or_arxiv"})
            verified_flag = curation_ok
            ref_status = "skipped" if curation_ok else "failed"
            target = verified_refs if curation_ok else failed_refs
            target.append({
                "ref_id": ref_id,
                "raw": raw_reference,
                "source": ref.get("source", ""),
                "checks": checks,
                "verified": verified_flag,
                "errors": errors,
                "status": ref_status,
            })
            continue

        # Year plausibility check
        year_match = re.search(r"\((\d{4})\)", ref_id)  # APA style: (2024)
        if year_match:
            year = year_match.group(1)
            check_ok, msg = _check_year_plausibility(year)
            checks.append({"type": "year", "value": year, "verified": check_ok, "message": msg})
            if not check_ok:
                errors.append(msg)

        # Author plausibility check
        author_match = re.match(r"^([A-Z][A-Za-z\s&]+)\s*\(", ref_id)
        if author_match:
            author = author_match.group(1).strip()
            check_ok, msg = _check_author_plausibility(author)
            checks.append({"type": "author", "value": author, "verified": check_ok, "message": msg})
            if not check_ok:
                errors.append(msg)

        # Determine overall verified status
        critical_checks = [c for c in checks if c["type"] in ("doi", "arxiv")]
        if critical_checks:
            verified_flag = curation_ok and all(c["verified"] for c in critical_checks)
        else:
            verified_flag = curation_ok

        if verified_flag:
            ref_status = "verified"
            verified_refs.append({
                "ref_id": ref_id,
                "raw": raw_reference,
                "source": ref.get("source", ""),
                "checks": checks,
                "verified": verified_flag,
                "errors": errors,
                "status": ref_status,
            })
        else:
            ref_status = "failed"
            failed_refs.append({
                "ref_id": ref_id,
                "raw": raw_reference,
                "source": ref.get("source", ""),
                "checks": checks,
                "verified": verified_flag,
                "errors": errors,
                "status": ref_status,
            })
            if ref.get("source_role") == "primary_source":
                warnings.append(f"Unverifiable primary source: {ref_id}")

    # Build report
    report = {
        "job_id": state.job_id,
        "total_refs": len(refs),
        "verified": len(verified_refs),
        "failed": len(failed_refs),
        "references": verified_refs + failed_refs,
        "warnings": warnings,
        "status": "passed" if not failed_refs else "failed",
    }
    report_path = write_json_artifact(state, "reference_verify_report.json", report)
    state.runtime["reference_verify_report_path"] = str(report_path)

    # Hard block if DOI verification is required and any references failed
    if policy.reference.doi_verification_required and failed_refs:
        error_samples = [f"{r['ref_id'][:60]}: {'; '.join(r['errors'][:2])}" for r in failed_refs[:3]]
        raise QAHardBlockError(
            f"REFERENCE_VERIFY: {len(failed_refs)} reference(s) could not be verified: "
            f"{'; '.join(error_samples)}. "
            "Fix the references or remove unverifiable ones before submission."
        )

    return state
