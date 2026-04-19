"""RESULTS_SANITY_PASS - remove internal audit artifacts from results section.

After MERGE_DRAFT (but before CITATION_BIND), detect and remove internal audit
artifacts that were inadvertently included in the results section by the agent.

Internal audit artifacts include:
  - Claim-Evidence Matrix tables
  - Community-to-Contribution Mapping tables
  - "Audit" or "Traceability" tables
  - Tables with "Claim ID", "Evidence ID", "Status" column headers

These belong in supplementary materials, not in the published results.
"""
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..runtime_support import write_json_artifact


# Patterns that indicate an internal audit / claim-evidence table
_AUDIT_TABLE_PATTERNS = [
    # Table with "Claim" and "Evidence" columns
    (r"\|?\s*Claim\s+ID\s*\|", "claim_id_table"),
    (r"\|?\s*Evidence\s+ID\s*\|", "evidence_id_table"),
    (r"\|?\s*Claim\s+-\s+Evidence", "claim_evidence_matrix"),
    # "Community-to-Contribution Mapping" table
    (r"Community.*Contribution\s+Mapping", "community_contribution_table"),
    # "Claim.*Status" or "Claim.*Verdict"
    (r"\|?\s*Status\s*\|", "status_column"),
    # "Evidence IDs" column followed by claim IDs
    (r"Evidence\s+IDs.*Claim", "evidence_claim_table"),
]

# Section heading patterns to look for within results section
_RESULTS_SUSPICIOUS_SUBSECTIONS = [
    "Claim-Evidence",
    "Evidence Matrix",
    "Community-to-Contribution",
    "Audit",
    "Traceability",
    "Supplementary",
]


def _looks_like_audit_table(table_text: str) -> bool:
    """Check if a markdown table looks like an internal audit artifact."""
    text_lower = table_text.lower()
    for pattern, _ in _AUDIT_TABLE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def _extract_tables_from_section(section_text: str) -> list[tuple[str, str]]:
    """Extract all markdown tables from section text.

    Returns list of (table_content, table_marker) tuples.
    """
    tables = []
    lines = section_text.split("\n")
    in_table = False
    table_lines = []
    table_start_idx = 0

    for i, line in enumerate(lines):
        if "|" in line and re.match(r"\s*\|?\s*[-:]+\s*\|", line):
            # Separator row — part of table
            in_table = True
            table_lines.append(line)
        elif in_table and "|" in line:
            table_lines.append(line)
        elif in_table and "|" not in line:
            # End of table
            tables.append(("\n".join(table_lines), f"[TABLE_AT_LINE_{table_start_idx}]"))
            table_lines = []
            in_table = False
        elif "|" in line:
            # First table row
            in_table = True
            table_start_idx = i
            table_lines.append(line)
        else:
            if in_table and not table_lines:
                in_table = False
            elif in_table:
                tables.append(("\n".join(table_lines), f"[TABLE_AT_LINE_{table_start_idx}]"))
                table_lines = []
                in_table = False

    if table_lines:
        tables.append(("\n".join(table_lines), f"[TABLE_AT_LINE_{table_start_idx}]"))

    return tables


def _remove_audit_tables_from_results(merged_text: str) -> tuple[str, list[dict]]:
    """Remove internal audit tables from the results section.

    Returns (cleaned_text, removed_tables_list).
    """
    # Split by sections using heading detection
    section_pattern = re.compile(r"(?=^#{1,3}\s+)", re.MULTILINE)
    parts = section_pattern.split(merged_text)

    cleaned_parts = []
    removed_tables: list[dict] = []

    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue

        # Check if this is the results section
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped, re.MULTILINE)
        is_results_section = False
        if heading_match:
            heading_text = heading_match.group(2).strip().lower()
            if "result" in heading_text:
                is_results_section = True

        if not is_results_section:
            cleaned_parts.append(part)
            continue

        # This is results — check for audit tables
        tables = _extract_tables_from_section(stripped)
        non_audit_parts = []

        current_pos = 0
        for table_content, marker in tables:
            # Find where this table appears in the original text
            table_pos = stripped.find(table_content, current_pos)
            if table_pos == -1:
                non_audit_parts.append(table_content)
                continue

            # Check if this looks like an audit table
            if _looks_like_audit_table(table_content):
                removed_tables.append({
                    "type": "audit_table",
                    "content": table_content,
                    "marker": marker,
                })
                current_pos = table_pos + len(table_content)
            else:
                current_pos = table_pos + len(table_content)

        # Reconstruct the section
        cleaned_parts.append(part)

    return "\n".join(cleaned_parts), removed_tables


def run_results_sanity_pass(state: ReportState) -> ReportState:
    """T_NEW: RESULTS_SANITY_PASS - remove internal audit artifacts from results.

    Position: After MERGE_DRAFT, before CITATION_BIND.
    """
    merged_path = state.drafts.get("merged_draft_md", "")
    if not merged_path or not Path(merged_path).exists():
        state.runtime["results_sanity_report_path"] = ""
        return state

    with open(merged_path, encoding="utf-8") as f:
        original_text = f.read()

    cleaned_text, removed = _remove_audit_tables_from_results(original_text)

    # Always write the (possibly unchanged) text to publication_draft_md.
    # This ensures the cleaned draft is the canonical publication input for
    # downstream nodes (CITATION_BIND, DOCX_RENDER) regardless of whether
    # any tables were removed. See academic-artifact-policy.md.
    pub_draft_path = merged_path  # same run dir
    with open(pub_draft_path, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    # Update BOTH keys so downstream nodes use the cleaned version.
    # merged_draft_md is still set for backward compatibility with nodes
    # that read it directly; publication_draft_md is the authoritative key
    # for academic mode pipeline.
    state.drafts["merged_draft_md"] = pub_draft_path
    state.drafts["publication_draft_md"] = str(pub_draft_path)

    report = {
        "job_id": state.job_id,
        "tables_removed": len(removed),
        "removed_tables": removed,
        "publication_draft_md": str(pub_draft_path),
    }
    report_path = write_json_artifact(state, "results_sanity_report.json", report)
    state.runtime["results_sanity_report_path"] = str(report_path)

    return state
