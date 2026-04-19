"""MAIN_TEXT_ARTIFACT_FILTER - strip internal markers and reject internal paths from publication draft.

ACADEMIC MODE (report_family == "academic_report"):
  This node runs after RESULTS_SANITY_PASS and before CITATION_BIND.
  It ensures the publication draft contains no internal traceability artifacts.

  Forbidden patterns in publication draft (hard block):
    - [Source: ...] markers
    - [CITE: ...] markers
    - .py filenames in prose context
    - Internal file paths (D:\, C:\, /home/, etc.)
    - Evidence IDs in running text (E001, evidence_ledger, etc.)
    - Claim-evidence matrix tables

  The cleaned version is written to publication_draft_md and replaces merged_draft_md
  in state for academic mode. See academic-artifact-policy.md.
"""
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact


# Patterns that indicate internal artifact contamination
_INTERNAL_PATTERNS = [
    # [Source: ...] and [CITE: ...] markers (already stripped by citation_bind,
    # but checked here as a belt-and-suspenders gate)
    (r"\[Source:\s*[^\]]+\]", "source_marker"),
    (r"\[CITE:\s*[^\]]+\]", "cite_marker"),
    (r"\[graphify:\s*[^\]]+\]", "graphify_marker"),
    # Python/module filenames in prose (not in code blocks, not in URLs)
    (r"(?<!`)(?<!\w)([a-zA-Z_][\w]*\.py)(?!\`)", "python_filename"),
    # Internal file paths
    (r"(?<!`)(?:[A-Z]:\\[^\s,;]+|/[home|Users|var|tmp][^\s,;]+)", "internal_path"),
    # Evidence IDs in running text (standalone alphanumeric codes)
    (r"(?<![\w`])(E\d{3,}|evidence_ledger|claim_matrix)(?![\w`])", "evidence_id"),
    # Claim-Evidence matrix tables
    (r"\|\s*Claim\s+ID\s*\|", "claim_evidence_table"),
    (r"\|\s*Evidence\s+ID\s*\|", "claim_evidence_table"),
]

# Patterns for text that is in a "safe" context (code blocks, URLs)
_SAFE_CONTEXTS = [
    r"```[\s\S]*?```",  # code blocks
    r"`[^`]+`",           # inline code
    r"https?://",          # URLs
    r"<[^>]+>",           # HTML/XML tags
]


def _is_in_safe_context(text: str, start: int, end: int, safe_patterns: list) -> bool:
    """Return True if the matched span is inside a code block, URL, or HTML tag."""
    prefix = text[:start]
    for safe in safe_patterns:
        # Find all safe regions before the match
        for m in re.finditer(safe, prefix):
            if m.start() <= start <= m.end():
                return True
    return False


def _scan_for_internal_artifacts(text: str) -> list[dict]:
    """Scan text for internal artifact patterns. Returns list of violations."""
    violations = []

    for pattern, artifact_type in _INTERNAL_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if _is_in_safe_context(text, m.start(), m.end(), _SAFE_CONTEXTS):
                continue  # Skip artifacts inside code blocks or URLs
            violations.append({
                "type": artifact_type,
                "matched": m.group(0),
                "position": m.start(),
                "context": text[max(0, m.start() - 40):m.end() + 40],
            })

    return violations


def _strip_markers(text: str) -> tuple[str, int]:
    """Strip [Source:], [CITE:], [graphify:] markers from text.

    Returns (stripped_text, count_stripped).
    """
    before = len(text)
    text = re.sub(r"\[Source:\s*[^\]]+\]", "", text)
    text = re.sub(r"\[CITE:\s*[^\]]+\]", "", text)
    text = re.sub(r"\[graphify:\s*[^\]]+\]", "", text)
    after = len(text)
    return text, before - after


def run_main_text_artifact_filter(state: ReportState) -> ReportState:
    """MAIN_TEXT_ARTIFACT_FILTER - ensure publication draft is artifact-free.

    Position: After RESULTS_SANITY_PASS, before CITATION_BIND (validate phase).

    Inputs:
      - state.drafts["merged_draft_md"] or state.drafts["publication_draft_md"]

    Outputs:
      - state.drafts["publication_draft_md"] — cleaned draft (canonical for academic)
      - main_text_filter_report.json

    Behavior:
      - Scans for forbidden patterns
      - Strips removable markers ([Source:], [CITE:], [graphify:])
      - Hard blocks on structural artifacts (.py filenames, internal paths, audit tables)
    """
    academic_mode = state.spec.get("report_family") == "academic_report"

    # Determine input path — prefer publication_draft_md if already set by RESULTS_SANITY_PASS
    input_key = (
        "publication_draft_md"
        if state.drafts.get("publication_draft_md")
        else "merged_draft_md"
    )
    input_path = state.drafts.get(input_key, "")
    if not input_path or not Path(input_path).exists():
        # Nothing to filter — pass through
        state.drafts["publication_draft_md"] = input_path
        state.runtime["main_text_filter_report_path"] = ""
        return state

    with open(input_path, encoding="utf-8") as f:
        original_text = f.read()

    text = original_text

    # Strip removable markers first
    text, markers_stripped = _strip_markers(text)

    # Scan for remaining violations
    violations = _scan_for_internal_artifacts(text)

    # Separate removable vs. structural violations
    removable_violations = [v for v in violations if v["type"] in ("source_marker", "cite_marker", "graphify_marker")]
    structural_violations = [v for v in violations if v["type"] not in ("source_marker", "cite_marker", "graphify_marker")]

    # Hard block on structural violations for academic mode
    if academic_mode and structural_violations:
        sample = structural_violations[:3]
        examples = "; ".join(f"{v['type']}: '{v['matched'][:50]}'" for v in sample)
        raise QAHardBlockError(
            f"MAIN_TEXT_ARTIFACT_FILTER: Structural internal artifact(s) found in publication draft "
            f"({len(structural_violations)} violations): {examples}. "
            "These must be removed before the document can be published."
        )

    # Write cleaned draft
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    pub_draft_path = run_dir / "publication_draft.md"
    with open(pub_draft_path, "w", encoding="utf-8") as f:
        f.write(text)

    # Update state: publication_draft_md is the canonical academic publication input
    state.drafts["publication_draft_md"] = str(pub_draft_path)
    # Also update merged_draft_md for backward compatibility
    if input_key != "merged_draft_md":
        state.drafts["merged_draft_md"] = str(pub_draft_path)

    report = {
        "job_id": state.job_id,
        "markers_stripped": markers_stripped,
        "total_violations": len(violations),
        "removable_violations": len(removable_violations),
        "structural_violations": len(structural_violations),
        "violations": violations[:20],  # Cap at 20 for report size
    }
    report_path = write_json_artifact(state, "main_text_filter_report.json", report)
    state.runtime["main_text_filter_report_path"] = str(report_path)

    return state
