"""MERGE_DRAFT node - concatenate sections + strip internal artifacts.

ABSORBS (per 禮6.2 of academic-report-simplify-retrospective):
  - results_sanity_pass: removes audit tables from results section
  - main_text_artifact_filter: strips [Source:], [CITE:], [graphify:] markers,
    scans for structural artifacts (.py filenames, internal paths, evidence IDs)

Position: After REVISION_APPLY, before CITATION_BIND in validate phase.

For revise_existing workflows, REVISION_APPLY already wrote merged_draft_md.
In that case this node still runs artifact stripping.
"""
import logging
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..policies import get_policy
from .section_contract import planned_section_ids
from .heading_dedup import dedupe_merged_draft

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Audit table detection (from results_sanity_pass)
# ------------------------------------------------------------------

_AUDIT_TABLE_PATTERNS = [
    (r"\|?\s*Claim\s+ID\s*\|", "claim_id_table"),
    (r"\|?\s*Evidence\s+ID\s*\|", "evidence_id_table"),
    (r"\|?\s*Claim\s+-\s+Evidence", "claim_evidence_matrix"),
    (r"Community.*Contribution\s+Mapping", "community_contribution_table"),
    (r"\|?\s*Status\s*\|", "status_column"),
    (r"Evidence\s+IDs.*Claim", "evidence_claim_table"),
]


def _looks_like_audit_table(table_text: str) -> bool:
    text_lower = table_text.lower()
    for pattern, _ in _AUDIT_TABLE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def _extract_tables_from_section(section_text: str) -> list[tuple[str, str]]:
    tables = []
    lines = section_text.split("\n")
    in_table = False
    table_lines = []
    table_start_idx = 0

    for i, line in enumerate(lines):
        if "|" in line and re.match(r"\s*\|?\s*[-:]+\s*\|", line):
            in_table = True
            table_lines.append(line)
        elif in_table and "|" in line:
            table_lines.append(line)
        elif in_table and "|" not in line:
            tables.append(("\n".join(table_lines), f"[TABLE_AT_LINE_{table_start_idx}]"))
            table_lines = []
            in_table = False
        elif "|" in line:
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


def _remove_audit_tables(merged_text: str) -> tuple[str, list[dict]]:
    """Remove internal audit tables from results section."""
    section_pattern = re.compile(r"(?=^#{1,3}\s+)", re.MULTILINE)
    parts = section_pattern.split(merged_text)
    cleaned_parts = []
    removed_tables = []

    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped, re.MULTILINE)
        is_results_section = False
        if heading_match:
            heading_text = heading_match.group(2).strip().lower()
            if "result" in heading_text:
                is_results_section = True

        if not is_results_section:
            cleaned_parts.append(part)
            continue

        tables = _extract_tables_from_section(stripped)
        current_pos = 0

        for table_content, marker in tables:
            table_pos = stripped.find(table_content, current_pos)
            if table_pos == -1:
                continue
            if _looks_like_audit_table(table_content):
                removed_tables.append({"type": "audit_table", "content": table_content[:200], "marker": marker})
                current_pos = table_pos + len(table_content)
            else:
                current_pos = table_pos + len(table_content)

        cleaned_parts.append(part)

    return "\n".join(cleaned_parts), removed_tables


# ------------------------------------------------------------------
# Internal artifact patterns (from main_text_artifact_filter)
# ------------------------------------------------------------------

_INTERNAL_PATTERNS = [
    (r"\[Source:\s*[^\]]+\]", "source_marker"),
    (r"\[CITE:\s*[^\]]+\]", "cite_marker"),
    (r"\[graphify:\s*[^\]]+\]", "graphify_marker"),
    (r"(?<!`)(?<!\w)([a-zA-Z_][\w]*\.py)(?!\`)", "python_filename"),
    (r"(?<!`)(?:[A-Z]:\\[^\s,;]+|/(?:home|Users|var|tmp)/[^\s,;]+)", "internal_path"),
    (r"(?<![\w`])(E\d{3,}|evidence_ledger|claim_matrix)(?![\w`])", "evidence_id"),
    (r"\|\s*Claim\s+ID\s*\|", "claim_evidence_table"),
    (r"\|\s*Evidence\s+ID\s*\|", "claim_evidence_table"),
]

_SAFE_CONTEXTS = [
    r"```[\s\S]*?```",
    r"`[^`]+`",
    r"https?://",
    r"<[^>]+>",
]

_SECTION_HEADING_ALIASES = {
    "methods": {"methodology", "research methodology"},
    "results": {"findings"},
    "discussion": {"analysis"},
}


def _is_in_safe_context(text: str, start: int, end: int) -> bool:
    prefix = text[:start]
    for safe in _SAFE_CONTEXTS:
        for m in re.finditer(safe, prefix):
            if m.start() <= start <= m.end():
                return True
    return False


def _strip_markers(text: str) -> tuple[str, int]:
    before = len(text)
    text = re.sub(r"\[Source:\s*[^\]]+\]", "", text)
    text = re.sub(r"\[CITE:\s*[^\]]+\]", "", text)
    text = re.sub(r"\[graphify:\s*[^\]]+\]", "", text)
    after = len(text)
    return text, before - after


def _scan_for_internal_artifacts(text: str) -> list[dict]:
    violations = []
    for pattern, artifact_type in _INTERNAL_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if _is_in_safe_context(text, m.start(), m.end()):
                continue
            violations.append({
                "type": artifact_type,
                "matched": m.group(0),
                "position": m.start(),
                "context": text[max(0, m.start() - 40):m.end() + 40],
            })
    return violations


def _canonical_section_title(section_id: str) -> str:
    return section_id.replace("_", " ").title()


def _canonicalize_section_content(section_id: str, content: str) -> str:
    """Normalize section-local heading structure before global merge.

    - Removes the outer section heading from agent-authored section drafts.
    - Demotes any additional level-1 headings inside a section to level-2.
    - Drops repeated empty duplicate headings such as multiple consecutive
      "## Data Source and Corpus" lines with no body content between them.
    """
    lines = content.splitlines()
    result: list[str] = []
    canonical_title = _canonical_section_title(section_id).strip().lower()
    alias_set = _SECTION_HEADING_ALIASES.get(section_id, set())

    first_heading_skipped = False
    last_heading_norm: str | None = None
    content_since_heading = True

    for line in lines:
        stripped = line.strip()
        heading_match = re.match(r"^(#+)\s+(.+)$", stripped)
        if not heading_match:
            if stripped:
                content_since_heading = True
            result.append(line)
            continue

        level = len(heading_match.group(1))
        heading_text = heading_match.group(2).strip()
        heading_norm = heading_text.lower()

        # Drop the outer section heading from the raw section draft.
        if not first_heading_skipped and (
            heading_norm == canonical_title
            or canonical_title in heading_norm
        ):
            first_heading_skipped = True
            last_heading_norm = None
            content_since_heading = False
            continue

        first_heading_skipped = True

        # If a section embeds another top-level heading, keep the text but
        # demote it into a subsection to preserve structure.
        if level == 1:
            level = 2

        if heading_norm in alias_set and level == 2:
            heading_text = heading_text.title()

        # Skip duplicate headings when nothing substantive appeared between them.
        if heading_norm == last_heading_norm and not content_since_heading:
            continue

        result.append(f"{'#' * level} {heading_text}")
        last_heading_norm = heading_norm
        content_since_heading = False

    # Trim leading/trailing blank lines after stripping the outer heading.
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()
    return "\n".join(result)


# ------------------------------------------------------------------
# Main node
# ------------------------------------------------------------------

def run_merge_draft(state: ReportState) -> ReportState:
    """MERGE_DRAFT - concatenate sections + strip internal artifacts.

    After merging sections in blueprint order, this node:
      1. Deduplicates headings
      2. Removes audit tables from results section
      3. Strips [Source:], [CITE:], [graphify:] markers
      4. Scans for structural artifacts (.py filenames, internal paths)
      5. Hard blocks on structural violations in academic mode

    Outputs:
      - merged_draft_md (concatenated sections)
      - publication_draft_md (artifact-free version for academic publication)
      - merge_draft_report.json
    """
    # Only revise_existing may reuse a merged draft from REVISION_APPLY.
    # new_draft must rebuild from section_drafts on every validate pass to avoid
    # stale revise_existing or prior-run draft contamination in checkpoints.
    existing = state.drafts.get("merged_draft_md", "")
    skip_merge = (
        state.spec.get("task_intent") == "revise_existing"
        and bool(existing and Path(existing).exists())
    )

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    removed_tables = []
    markers_stripped = 0

    if skip_merge:
        # Still read and process the existing merged draft
        merged_path = Path(existing)
        merged_text = merged_path.read_text(encoding="utf-8")
        logger.info(f"[MERGE_DRAFT] Using existing merged draft from REVISION_APPLY")
    else:
        # Build merged draft from sections
        blueprint = state.plan.get("blueprint", {})
        section_order = planned_section_ids(blueprint, state.plan.get("outline") or {})
        section_drafts = state.drafts.get("section_drafts", {})

        if not section_order:
            raise QAHardBlockError("Blueprint has no section order")
        if not section_drafts:
            raise QAHardBlockError("No section drafts to merge")

        merged_sections = []
        for section_id in section_order:
            section_path = section_drafts.get(section_id)
            if section_path:
                try:
                    with open(section_path, encoding="utf-8") as f:
                        content = f.read()
                    if not content.strip():
                        raise QAHardBlockError(f"Section draft is empty: {section_id}")
                    if "This section is under development" in content:
                        raise QAHardBlockError(f"Section draft is placeholder content: {section_id}")
                    normalized = _canonicalize_section_content(section_id, content)
                    section_title = _canonical_section_title(section_id)
                    merged_sections.append(f"# {section_title}\n\n{normalized}".strip())
                except QAHardBlockError:
                    raise
                except Exception as exc:
                    raise QAHardBlockError(f"Failed to read section draft {section_id}: {exc}") from exc
            else:
                raise QAHardBlockError(f"Missing section draft: {section_id}")

        merged_md = "\n\n".join(merged_sections)
        if not merged_md.strip():
            raise QAHardBlockError("Merged draft is empty")

        merged_text = merged_md

    # Step 1: Deduplicate headings
    merged_text = dedupe_merged_draft(merged_text)
    logger.info(f"[MERGE_DRAFT] Heading dedup applied, {len(merged_text)} chars")

    # Step 2: Remove audit tables from results section
    merged_text, removed_tables = _remove_audit_tables(merged_text)

    # Step 3: Strip [Source:] and [graphify:] markers only.
    # NOTE: [CITE:...] markers are preserved because CITATION_BIND needs them in merged_draft_md.
    # to resolve and audit citations. Stripping [CITE:] here breaks the citation audit chain
    # (cite_id not found in merged_md at citation_bind).
    before = len(merged_text)
    merged_text = re.sub(r"\[Source:\s*[^\]]+\]", "", merged_text)
    merged_text = re.sub(r"\[graphify:\s*[^\]]+\]", "", merged_text)
    markers_stripped = before - len(merged_text)

    # Step 4: Scan for structural artifacts
    violations = _scan_for_internal_artifacts(merged_text)
    removable_violations = [v for v in violations if v["type"] in ("source_marker", "cite_marker", "graphify_marker")]
    structural_violations = [v for v in violations if v["type"] not in ("source_marker", "cite_marker", "graphify_marker")]

    # Step 5: Hard block on structural violations per policy
    family = state.spec.get("report_profile", "academic_paper")
    policy = get_policy(family)
    if policy.figure.audit_table_hard_block and structural_violations:
        sample = structural_violations[:3]
        examples = "; ".join(f"{v['type']}: '{v['matched'][:50]}'" for v in sample)
        raise QAHardBlockError(
            f"MERGE_DRAFT: Structural internal artifact(s) found in publication draft "
            f"({len(structural_violations)} violations): {examples}. "
            "These must be removed before the document can be published."
        )

    # Write merged draft
    merged_path = run_dir / "merged_draft.md"
    with open(merged_path, "w", encoding="utf-8") as f:
        f.write(merged_text)
    state.drafts["merged_draft_md"] = str(merged_path)

    # Write publication draft (same content after artifact stripping)
    pub_draft_path = run_dir / "publication_draft.md"
    with open(pub_draft_path, "w", encoding="utf-8") as f:
        f.write(merged_text)
    state.drafts["publication_draft_md"] = str(pub_draft_path)

    # Write report
    report = {
        "job_id": state.job_id,
        "markers_stripped": markers_stripped,
        "tables_removed": len(removed_tables),
        "total_violations": len(violations),
        "structural_violations": len(structural_violations),
        "removable_violations": len(removable_violations),
        "violations": violations[:20],
    }
    report_path = write_json_artifact(state, "merge_draft_report.json", report)

    logger.info(
        f"[MERGE_DRAFT] Done: {markers_stripped} markers stripped, "
        f"{len(removed_tables)} audit tables removed, "
        f"{len(structural_violations)} structural violations"
    )

    return state
