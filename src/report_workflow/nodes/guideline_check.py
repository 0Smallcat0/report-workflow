"""GUIDELINE_CHECK node - PRISMA / STROBE compliance checking.

Sits between CONSISTENCY_CHECK and QA_GATE.
Only runs when state.spec["selected_guidelines"] contains 'PRISMA' or 'STROBE'.

For each required hard-severity item:
  - Check if any detection_hints keyword appears in the relevant section(s)
  - Missing hard item → QAHardBlockError
  - Missing soft item → warning (no block)
  - Missing warn item → informational only

Output: guideline_report.json
"""
import json
import re
from pathlib import Path
from typing import Optional

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _load_guideline(name: str) -> dict | None:
    """Load a guideline JSON by canonical name (PRISMA, STROBE)."""
    guideline_dir = Path(__file__).parent.parent / "guidelines"
    path = guideline_dir / f"{name}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# Core checking logic
# ------------------------------------------------------------------

# Keywords to skip (too generic — cause false positives)
_STOP_WORDS: set[str] = {
    "objective", "aim", "goal", "purpose",
    "result", "results", "outcome", "outcomes",
    "method", "methods", "study", "studies",
    "data", "analysis", "analyzed", " table ",
}


def _check_section_keywords(
    section_content: str,
    hints: list[str],
) -> bool:
    """Return True if any detection hint phrase is found in section content.

    Performs case-insensitive whole-word matching for each hint phrase.
    """
    if not section_content or not hints:
        return False
    text_lower = section_content.lower()
    for hint in hints:
        hint_lower = hint.lower().strip()
        if not hint_lower:
            continue
        # Skip very generic hints that produce false positives
        if hint_lower in _STOP_WORDS:
            continue
        # Whole-word / phrase match using word boundary
        pattern = r"\b" + re.escape(hint_lower) + r"\b"
        if re.search(pattern, text_lower):
            return True
    return False


def _split_by_sections(merged_text: str) -> dict[str, str]:
    """Split merged markdown into section_id → content mapping.

    Uses '# Section Name' headings (case-insensitive) as delimiters.
    """
    sections: dict[str, str] = {}
    lines_by_section: list[tuple[str, list[str]]] = []
    current_section = "preamble"
    current_lines: list[str] = []

    for line in merged_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            # Flush previous section
            if current_lines:
                lines_by_section.append((current_section, current_lines))
                current_lines = []
            # New section id derived from heading text
            heading = stripped[2:].strip().lower().replace(" ", "_")
            current_section = heading[:48]
        current_lines.append(line)

    # Flush last section
    if current_lines:
        lines_by_section.append((current_section, current_lines))

    for sid, lines in lines_by_section:
        sections[sid] = "\n".join(lines).strip()

    return sections


def _check_guideline(
    guideline: dict,
    section_content_map: dict[str, str],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Run all checks for a single guideline.

    Returns (hard_violations, soft_violations, warn_violations).
    """
    hard: list[dict] = []
    soft: list[dict] = []
    warn: list[dict] = []

    for item in guideline.get("items", []):
        if not item.get("required", False):
            continue

        severity = item.get("severity", "soft")
        if severity not in ("hard", "soft", "warn"):
            severity = "soft"

        item_id = item.get("item_id", "?")
        description = item.get("description", "")
        covers_sections: list[str] = item.get("covers_sections", [])
        detection_hints: list[str] = item.get("detection_hints", [])

        # Collect content from relevant sections
        relevant_content = ""
        if covers_sections:
            for sec_id in covers_sections:
                content = section_content_map.get(sec_id, "")
                relevant_content += " " + content
        else:
            # Check entire document
            relevant_content = " ".join(section_content_map.values())

        found = _check_section_keywords(relevant_content, detection_hints)

        violation = {
            "item_id": item_id,
            "description": description,
            "severity": severity,
            "covers_sections": covers_sections,
            "detection_hints": detection_hints,
            "found": found,
        }

        if severity == "hard" and not found:
            hard.append(violation)
        elif severity == "soft" and not found:
            soft.append(violation)
        elif severity == "warn" and not found:
            warn.append(violation)

    return hard, soft, warn


# ------------------------------------------------------------------
# Main node
# ------------------------------------------------------------------

def run_guideline_check(state: ReportState) -> ReportState:
    """T14: GUIDELINE_CHECK - PRISMA / STROBE compliance.

    Only runs when selected_guidelines contains 'PRISMA' or 'STROBE'.
    Reads merged_draft_md and outline.json.
    Writes guideline_report.json.
    Raises QAHardBlockError on any hard violation.
    """
    selected: list[str] = state.spec.get("selected_guidelines", [])
    if not selected:
        return state

    active: list[str] = [g for g in selected if g.upper() in ("PRISMA", "STROBE")]
    if not active:
        return state

    merged_path = state.drafts.get("merged_draft_md", "")
    if not merged_path or not Path(merged_path).exists():
        # Nothing to check yet
        state.qa["guideline_report_path"] = ""
        return state

    merged_text = Path(merged_path).read_text(encoding="utf-8")
    section_map = _split_by_sections(merged_text)

    all_hard: list[dict] = []
    all_soft: list[dict] = []
    all_warn: list[dict] = []

    for guideline_name in active:
        guideline = _load_guideline(guideline_name)
        if not guideline:
            continue
        hard, soft, warn = _check_guideline(guideline, section_map)
        all_hard.extend(hard)
        all_soft.extend(soft)
        all_warn.extend(warn)

    report = {
        "job_id": state.job_id,
        "guidelines_checked": active,
        "hard_violations": all_hard,
        "soft_violations": all_soft,
        "warn_violations": all_warn,
        "total_hard": len(all_hard),
        "total_soft": len(all_soft),
        "total_warn": len(all_warn),
    }

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "guideline_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    state.qa["guideline_report_path"] = str(report_path)

    # Hard gate: any hard violation → QA_GATE hard-fail
    if all_hard:
        missing = [f"{v['item_id']}: {v['description']}" for v in all_hard]
        raise QAHardBlockError(
            f"guideline violations (hard): " + "; ".join(missing[:5])
        )

    return state
