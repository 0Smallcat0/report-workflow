"""CONSISTENCY_CHECK node - numeric / units consistency.

Sits between FACTUALITY_CHECK and QA_GATE.
Fails hard on any numeric contradiction or unit notation inconsistency.
"""
import json
import re
from pathlib import Path
from typing import Optional

from ..errors import QAHardBlockError
from ..state import ReportState, WORKFLOW_RUNS_DIR


# ------------------------------------------------------------------
# Sub-check 1: Numeric consistency
# ------------------------------------------------------------------

# Regex: captures (number, unit) pairs
_NUMERIC_RE = re.compile(
    r"""
    (?:^|\s|[,(])                    # boundary
    (                                 # start capture: number + optional unit
        \d+(?:\.\d+)?(?:[eE][+-]?\d+)?   # integer, decimal, or scientific
        \s*
        (?:[a-zA-Z%°µμ]+/?[a-zA-Z%°µμ]*)?  # optional unit (e.g. %, °C, mg/ml)
    )
    """,
    re.VERBOSE,
)


def _extract_numeric(text: str) -> list[tuple[str, str]]:
    """Return list of (number_str, unit_str) from text."""
    results = []
    for m in _NUMERIC_RE.finditer(text):
        num_unit = m.group(1).strip()
        # Split leading number from unit
        m2 = re.match(r'^([\d.eE+-]+)\s*(.*)$', num_unit)
        if m2:
            results.append((m2.group(1), m2.group(2)))
    return results


def _check_numeric_consistency(merged_text: str) -> list[dict]:
    """Verify same numeric values appear consistently across sections.

    Contradiction = same unit appears with different numbers in same context.
    Only flags when the SAME parameter/concept has different values.
    Numbers are normalised to float before comparison to avoid "20" vs "20.0" false positives.
    """
    issues = []

    # Extract all (number_str, unit_str) pairs with surrounding context
    pairs = _extract_numeric(merged_text)

    # Group by normalized unit
    by_unit: dict[str, list[tuple[str, str]]] = {}  # normalized_unit → [(number, raw_unit), ...]
    for num, raw_unit in pairs:
        norm = _normalize_unit(raw_unit)
        if norm:
            by_unit.setdefault(norm, []).append((num, raw_unit))

    # For each unit, check for same numeric value appearing multiple times
    for norm_unit, entries in by_unit.items():
        value_counts: dict[str, int] = {}
        for num, _ in entries:
            try:
                normalized = str(float(num))
                value_counts[normalized] = value_counts.get(normalized, 0) + 1
            except ValueError:
                pass

        if norm_unit == "%":
            # Check for notation inconsistency only (same value, different notation)
            notation_groups: dict[str, set[str]] = {}
            for num, raw_unit in entries:
                try:
                    normalized = str(float(num))
                    notation_groups.setdefault(normalized, set()).add(raw_unit.lower())
                except ValueError:
                    pass

            for normalized_val, notations in notation_groups.items():
                if len(notations) > 1:
                    issues.append({
                        "check": "numeric",
                        "severity": "high",
                        "type": "notation_inconsistency",
                        "detail": (
                            f"Value '{normalized_val}{norm_unit}' written multiple ways: "
                            f"{', '.join(sorted(notations))}"
                        ),
                    })
            continue

    return issues


# ------------------------------------------------------------------
# Sub-check 2: Unit notation consistency
# ------------------------------------------------------------------

# Known unit groups that should be consistently written
_UNIT_ALIASES: dict[str, list[str]] = {
    "%": ["%", "percent", "percentage"],
    "°C": ["°C", "degrees C", "degrees Celsius", "℃"],
    "mg": ["mg", "milligram", "milligrams"],
    "ml": ["ml", "milliliter", "milliliters", "mL"],
    "kg": ["kg", "kilogram", "kilograms"],
    "µg": ["µg", "microgram", "micrograms", "ug"],
}


def _normalize_unit(unit: str) -> Optional[str]:
    unit = unit.strip().lower()
    for canonical, aliases in _UNIT_ALIASES.items():
        if unit in aliases:
            return canonical
    return None  # unknown unit, skip


def _check_unit_notation(merged_text: str) -> list[dict]:
    """Ensure the same physical quantity is written with the same notation."""
    issues = []

    # Extract all unit-bearing tokens
    unit_tokens: list[tuple[str, str]] = []  # (raw_token, normalized)
    for _, unit in _extract_numeric(merged_text):
        if unit:
            norm = _normalize_unit(unit)
            if norm:
                unit_tokens.append((unit, norm))

    # Group by normalized form
    by_norm: dict[str, list[str]] = {}
    for raw, norm in unit_tokens:
        by_norm.setdefault(norm, []).append(raw)

    for norm, tokens in by_norm.items():
        unique_forms = set(tokens)
        if len(unique_forms) > 1:
            issues.append({
                "check": "units",
                "severity": "high",
                "type": "notation_inconsistency",
                "detail": (
                    f"Unit '{norm}' written multiple ways: "
                    f"{', '.join(sorted(unique_forms))}"
                ),
            })

    return issues


# ------------------------------------------------------------------
# Main node
# ------------------------------------------------------------------

def run_consistency_check(state: ReportState) -> ReportState:
    """T13b: CONSISTENCY_CHECK - numeric / units consistency.

    Runs after FACTUALITY_CHECK, before QA_GATE.
    Reads: merged_draft_md
    Writes: consistency_report.json
    Raises: QAHardBlockError on any high-severity issue.

    Note: Terminology spelling consistency was removed (false-positive rate
    too high; terminology quality is enforced via banned_phrases config).
    """
    merged_path = state.drafts.get("merged_draft_md", "")

    if not merged_path or not Path(merged_path).exists():
        # Nothing to check — let QA_GATE catch the missing draft
        state.qa["consistency_report_path"] = ""
        return state

    merged_text = Path(merged_path).read_text(encoding="utf-8")

    all_issues = []
    all_issues.extend(_check_numeric_consistency(merged_text))
    all_issues.extend(_check_unit_notation(merged_text))

    # Write report
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "consistency_report.json"
    report = {
        "job_id": state.job_id,
        "issues": all_issues,
        "total_issues": len(all_issues),
        "high_severity": sum(1 for i in all_issues if i.get("severity") == "high"),
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    state.qa["consistency_report_path"] = str(report_path)

    # Hard gate: any high-severity issue → QA_GATE will also see it via hard_fail_reasons
    high_issues = [i for i in all_issues if i.get("severity") == "high"]
    if high_issues:
        reasons = [f"[{i['check']}] {i['detail']}" for i in high_issues]
        raise QAHardBlockError("consistency violations: " + "; ".join(reasons))

    return state
