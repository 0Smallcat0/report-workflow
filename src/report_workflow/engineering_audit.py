"""Engineering-lab numeric, unit, and calculation audit helpers."""
from __future__ import annotations

import ast
import json
import math
import operator
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact_contract import load_jsonl_without_contract
from .runtime_support import write_json_artifact
from .state import ReportState, run_dir_for


MEASUREMENT_RE = re.compile(
    r"(?<![\w.])"
    r"(?P<value>-?\d+(?:\.\d+)?)"
    r"\s*"
    r"(?P<unit>°C|℃|%|μg|ug|mg|g|kg|mm|cm|m|km|ms|s|"
    r"mV|V|mA|A|ohm|Ω|kΩ|W|N|Pa|Hz|"
    r"毫米|公厘|厘米|公分|公尺|米|公里|"
    r"毫秒|秒|公克|克|公斤|伏特|安培|歐姆|瓦特|牛頓)"
    r"(?=$|[\s,.;:)\]，。；：、])",
    re.IGNORECASE,
)

NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
EQUATION_RE = re.compile(
    r"(?P<expr>(?:-?\d+(?:\.\d+)?|\s|[()+\-*/×÷]){3,})"
    r"=\s*(?P<result>-?\d+(?:\.\d+)?)"
)

UNIT_ALIASES: dict[str, tuple[str, str]] = {
    "%": ("ratio", "%"),
    "mm": ("length", "mm"),
    "毫米": ("length", "mm"),
    "公厘": ("length", "mm"),
    "cm": ("length", "cm"),
    "厘米": ("length", "cm"),
    "公分": ("length", "cm"),
    "m": ("length", "m"),
    "米": ("length", "m"),
    "公尺": ("length", "m"),
    "km": ("length", "km"),
    "公里": ("length", "km"),
    "ms": ("time", "ms"),
    "毫秒": ("time", "ms"),
    "s": ("time", "s"),
    "秒": ("time", "s"),
    "mg": ("mass", "mg"),
    "μg": ("mass", "ug"),
    "ug": ("mass", "ug"),
    "g": ("mass", "g"),
    "克": ("mass", "g"),
    "公克": ("mass", "g"),
    "kg": ("mass", "kg"),
    "公斤": ("mass", "kg"),
    "mv": ("voltage", "mV"),
    "mV": ("voltage", "mV"),
    "v": ("voltage", "V"),
    "V": ("voltage", "V"),
    "伏特": ("voltage", "V"),
    "ma": ("current", "mA"),
    "mA": ("current", "mA"),
    "a": ("current", "A"),
    "A": ("current", "A"),
    "安培": ("current", "A"),
    "ohm": ("resistance", "ohm"),
    "Ω": ("resistance", "ohm"),
    "kΩ": ("resistance", "kohm"),
    "歐姆": ("resistance", "ohm"),
    "w": ("power", "W"),
    "W": ("power", "W"),
    "瓦特": ("power", "W"),
    "n": ("force", "N"),
    "N": ("force", "N"),
    "牛頓": ("force", "N"),
    "pa": ("pressure", "Pa"),
    "Pa": ("pressure", "Pa"),
    "hz": ("frequency", "Hz"),
    "Hz": ("frequency", "Hz"),
    "°c": ("temperature", "degC"),
    "°C": ("temperature", "degC"),
    "℃": ("temperature", "degC"),
}


@dataclass
class Measurement:
    value: float
    raw_value: str
    raw_unit: str
    dimension: str
    canonical_unit: str
    context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "raw_value": self.raw_value,
            "raw_unit": self.raw_unit,
            "dimension": self.dimension,
            "canonical_unit": self.canonical_unit,
            "context": self.context,
        }


@dataclass
class TableSnapshot:
    evidence_id: str
    source_file_name: str
    rows: list[list[str]]

    def text(self) -> str:
        return "\n".join(" | ".join(row) for row in self.rows)

    def to_dict(self) -> dict[str, Any]:
        measurements = extract_measurements(self.text())
        return {
            "evidence_id": self.evidence_id,
            "source_file_name": self.source_file_name,
            "row_count": len(self.rows),
            "column_count": max((len(row) for row in self.rows), default=0),
            "measurements": [item.to_dict() for item in measurements[:25]],
            "numbers": _extract_numbers(self.text())[:50],
            "preview": [row[:8] for row in self.rows[:4]],
        }


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def _normalize_unit(unit: str) -> tuple[str, str]:
    raw = _normalize_text(unit).strip()
    return UNIT_ALIASES.get(raw, UNIT_ALIASES.get(raw.casefold(), ("unknown", raw)))


def _context(text: str, start: int, end: int, radius: int = 48) -> str:
    return " ".join(text[max(0, start - radius): min(len(text), end + radius)].split())


def extract_measurements(text: str) -> list[Measurement]:
    normalized = _normalize_text(text)
    measurements: list[Measurement] = []
    for match in MEASUREMENT_RE.finditer(normalized):
        raw_unit = match.group("unit")
        dimension, canonical = _normalize_unit(raw_unit)
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        measurements.append(
            Measurement(
                value=value,
                raw_value=match.group("value"),
                raw_unit=raw_unit,
                dimension=dimension,
                canonical_unit=canonical,
                context=_context(normalized, match.start(), match.end()),
            )
        )
    return measurements


def _load_report_text(state: ReportState) -> str:
    merged_path = state.drafts.get("merged_draft_md") or state.drafts.get("merged_draft_cited_md")
    if merged_path and Path(merged_path).exists():
        return Path(merged_path).read_text(encoding="utf-8")

    run_dir = run_dir_for(state)
    section_dir = run_dir / "section_drafts"
    if section_dir.exists():
        parts = [path.read_text(encoding="utf-8") for path in sorted(section_dir.glob("*.md"))]
        if parts:
            return "\n\n".join(parts)

    structured_path = run_dir / "structured_drafts.json"
    if structured_path.exists():
        try:
            payload = json.loads(structured_path.read_text(encoding="utf-8"))
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return structured_path.read_text(encoding="utf-8", errors="replace")
    return ""


def _load_claim_matrix(state: ReportState) -> dict:
    run_dir = run_dir_for(state)
    path = run_dir / "claim_matrix.json"
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return state.plan.get("claim_matrix") or {}


def _load_evidence(state: ReportState) -> list[dict]:
    path = state.sources.get("evidence_ledger_path")
    if path and Path(path).exists():
        try:
            return load_jsonl_without_contract(path)
        except Exception:
            return []
    run_dir = run_dir_for(state)
    fallback = run_dir / "evidence_ledger.jsonl"
    if fallback.exists():
        try:
            return load_jsonl_without_contract(fallback)
        except Exception:
            return []
    return []


def _extract_numbers(text: str) -> list[str]:
    values: list[str] = []
    for match in NUMBER_RE.finditer(_normalize_text(text)):
        raw = match.group(0)
        try:
            values.append(str(float(raw)))
        except ValueError:
            values.append(raw)
    return values


def _extract_support_numbers(text: str) -> list[str]:
    normalized = _normalize_text(text)
    values: list[str] = []
    for match in NUMBER_RE.finditer(normalized):
        prefix = normalized[max(0, match.start() - 12):match.start()].casefold()
        if re.search(r"(table|figure|fig\.?)\s*$", prefix):
            continue
        raw = match.group(0)
        try:
            values.append(str(float(raw)))
        except ValueError:
            values.append(raw)
    return values


def _rows_from_table_data(table_data: Any) -> list[list[str]]:
    if not isinstance(table_data, list):
        return []
    rows: list[list[str]] = []
    for row in table_data:
        if isinstance(row, list):
            rows.append([str(cell) for cell in row])
        elif isinstance(row, dict):
            if not rows:
                rows.append([str(key) for key in row.keys()])
            rows.append([str(value) for value in row.values()])
    return rows


def _rows_from_json_content(content: str) -> list[list[str]]:
    try:
        payload = json.loads(content)
    except Exception:
        return []
    if isinstance(payload, dict):
        return [[str(key) for key in payload.keys()], [str(value) for value in payload.values()]]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        headers: list[str] = []
        for item in payload:
            for key in item.keys():
                if key not in headers:
                    headers.append(str(key))
        rows = [headers]
        for item in payload:
            rows.append([str(item.get(header, "")) for header in headers])
        return rows
    return []


def _rows_from_pipe_text(content: str) -> list[list[str]]:
    lines = [line.strip() for line in str(content or "").splitlines() if "|" in line]
    rows: list[list[str]] = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not any(cells):
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
            continue
        rows.append(cells)
    return rows


def _table_snapshot_from_evidence(entry: dict) -> TableSnapshot | None:
    rows = _rows_from_table_data(entry.get("table_data"))
    if not rows:
        content = str(entry.get("content") or "")
        if entry.get("granularity") == "table_row" or entry.get("file_type") in {"csv", "xlsx"}:
            rows = _rows_from_json_content(content)
        if not rows and ("|" in content or entry.get("granularity") == "table"):
            rows = _rows_from_pipe_text(content)
    if not rows:
        return None
    return TableSnapshot(
        evidence_id=str(entry.get("evidence_id") or ""),
        source_file_name=str(entry.get("source_file_name") or ""),
        rows=rows,
    )


def _table_snapshots(evidence: list[dict]) -> list[TableSnapshot]:
    snapshots: list[TableSnapshot] = []
    for entry in evidence:
        snapshot = _table_snapshot_from_evidence(entry)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


def _measurement_key(measurement: Measurement) -> tuple[float, str]:
    return (round(measurement.value, 9), measurement.canonical_unit)


def _claim_unit_support_issues(claim_matrix: dict, evidence: list[dict]) -> list[dict]:
    evidence_by_id = {str(row.get("evidence_id")): row for row in evidence if row.get("evidence_id")}
    issues: list[dict] = []
    for claim in claim_matrix.get("claims", []) or []:
        claim_id = str(claim.get("claim_id") or "")
        claim_measurements = extract_measurements(str(claim.get("claim_text") or ""))
        if not claim_measurements:
            continue
        linked_content = "\n".join(
            str(evidence_by_id.get(str(eid), {}).get("content") or evidence_by_id.get(str(eid), {}).get("quote") or "")
            for eid in claim.get("evidence_ids", []) or []
        )
        evidence_keys = {_measurement_key(item) for item in extract_measurements(linked_content)}
        for measurement in claim_measurements:
            if _measurement_key(measurement) not in evidence_keys:
                issues.append({
                    "severity": "warning",
                    "check": "claim_unit_support",
                    "claim_id": claim_id,
                    "detail": (
                        f"Claim measurement {measurement.raw_value}{measurement.raw_unit} "
                        "was not found with the same normalized unit in linked evidence."
                    ),
                    "hint": "Link evidence containing the same measurement, or rewrite the claim to match source units.",
                    "measurement": measurement.to_dict(),
                })
    return issues


def _claim_table_support_issues(claim_matrix: dict, evidence: list[dict]) -> list[dict]:
    evidence_by_id = {str(row.get("evidence_id")): row for row in evidence if row.get("evidence_id")}
    issues: list[dict] = []
    for claim in claim_matrix.get("claims", []) or []:
        claim_id = str(claim.get("claim_id") or "")
        claim_text = str(claim.get("claim_text") or "")
        claim_numbers = set(_extract_support_numbers(claim_text))
        claim_measurements = {_measurement_key(item) for item in extract_measurements(claim_text)}
        if not claim_numbers and not claim_measurements:
            continue

        linked_tables = [
            snapshot
            for eid in claim.get("evidence_ids", []) or []
            if (snapshot := _table_snapshot_from_evidence(evidence_by_id.get(str(eid), {})))
        ]
        if not linked_tables:
            continue

        table_text = "\n".join(snapshot.text() for snapshot in linked_tables)
        table_numbers = set(_extract_numbers(table_text))
        table_measurements = {_measurement_key(item) for item in extract_measurements(table_text)}
        missing_numbers = sorted(claim_numbers - table_numbers)
        missing_measurements = sorted(claim_measurements - table_measurements)
        if missing_numbers:
            issues.append({
                "severity": "warning",
                "check": "claim_table_value_support",
                "claim_id": claim_id,
                "detail": (
                    "Claim numeric value(s) not found in linked table evidence: "
                    + ", ".join(missing_numbers[:12])
                ),
                "hint": "Check the source table row, then fix the claim value or link the correct table evidence.",
                "linked_table_evidence_ids": [snapshot.evidence_id for snapshot in linked_tables],
            })
        if table_measurements and missing_measurements:
            issues.append({
                "severity": "warning",
                "check": "claim_table_unit_support",
                "claim_id": claim_id,
                "detail": "Claim measurement/unit pair is not present in linked table evidence.",
                "hint": "Use the same value and unit as the table, or show an explicit conversion.",
                "linked_table_evidence_ids": [snapshot.evidence_id for snapshot in linked_tables],
            })
    return issues


def _unit_notation_issues(measurements: list[Measurement]) -> list[dict]:
    by_unit: dict[str, set[str]] = {}
    for measurement in measurements:
        if measurement.dimension == "unknown":
            continue
        by_unit.setdefault(measurement.canonical_unit, set()).add(measurement.raw_unit)

    issues: list[dict] = []
    for canonical, raw_forms in sorted(by_unit.items()):
        if len(raw_forms) <= 1:
            continue
        issues.append({
            "severity": "warning",
            "check": "unit_notation",
            "canonical_unit": canonical,
            "detail": f"Unit {canonical!r} appears in multiple notations: {', '.join(sorted(raw_forms))}",
            "hint": "Use one notation consistently throughout the engineering report.",
        })
    return issues


def _mixed_dimension_unit_issues(measurements: list[Measurement]) -> list[dict]:
    by_dimension: dict[str, set[str]] = {}
    for measurement in measurements:
        if measurement.dimension in {"unknown", "ratio"}:
            continue
        by_dimension.setdefault(measurement.dimension, set()).add(measurement.canonical_unit)

    issues: list[dict] = []
    for dimension, units in sorted(by_dimension.items()):
        if len(units) <= 1:
            continue
        issues.append({
            "severity": "info",
            "check": "mixed_units_for_dimension",
            "dimension": dimension,
            "detail": f"{dimension} values use multiple units: {', '.join(sorted(units))}",
            "hint": "Confirm conversions are intentional and show conversion steps in calculations when needed.",
        })
    return issues


def _missing_unit_issues(text: str, measurements: list[Measurement]) -> list[dict]:
    measurement_spans = {
        (match.start(), match.end())
        for match in MEASUREMENT_RE.finditer(_normalize_text(text))
    }
    issues: list[dict] = []
    normalized = _normalize_text(text)
    for match in NUMBER_RE.finditer(normalized):
        if any(start <= match.start() < end for start, end in measurement_spans):
            continue
        raw = match.group(0)
        if raw in {"0", "1"}:
            continue
        if re.fullmatch(r"19\d{2}|20\d{2}", raw):
            continue
        surrounding = _context(normalized, match.start(), match.end())
        if "[CITE:" in surrounding or "E0" in surrounding:
            continue
        issues.append({
            "severity": "info",
            "check": "number_without_unit",
            "detail": f"Number {raw!r} appears without an adjacent recognized unit.",
            "hint": "For measured data or calculations, include the unit or clarify that the number is dimensionless.",
            "context": surrounding,
        })
        if len(issues) >= 25:
            break
    return issues


ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_numeric_expr(expr: str) -> float:
    node = ast.parse(expr, mode="eval")

    def eval_node(current: ast.AST) -> float:
        if isinstance(current, ast.Expression):
            return eval_node(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, (int, float)):
            return float(current.value)
        if isinstance(current, ast.BinOp) and type(current.op) in ALLOWED_BINOPS:
            return ALLOWED_BINOPS[type(current.op)](eval_node(current.left), eval_node(current.right))
        if isinstance(current, ast.UnaryOp) and type(current.op) in ALLOWED_UNARY:
            return ALLOWED_UNARY[type(current.op)](eval_node(current.operand))
        raise ValueError("unsupported expression")

    return eval_node(node)


def _calculation_issues(text: str) -> tuple[list[dict], int]:
    issues: list[dict] = []
    checked = 0
    normalized = _normalize_text(text).replace("×", "*").replace("÷", "/")
    for match in EQUATION_RE.finditer(normalized):
        expr = match.group("expr").strip()
        if not re.search(r"[+\-*/]", expr):
            continue
        try:
            expected = float(match.group("result"))
            actual = _eval_numeric_expr(expr)
        except Exception:
            continue
        checked += 1
        tolerance = max(1e-6, abs(expected) * 1e-4)
        if not math.isclose(actual, expected, rel_tol=1e-4, abs_tol=tolerance):
            issues.append({
                "severity": "warning",
                "check": "calculation_result",
                "detail": f"Calculation {expr} = {expected:g} does not match evaluated result {actual:g}.",
                "hint": "Recalculate this equation or show rounding assumptions.",
                "expression": expr,
                "reported_result": expected,
                "evaluated_result": actual,
            })
    return issues, checked


def run_engineering_audit(state: ReportState) -> dict[str, Any]:
    """Write engineering_audit_report.json without mutating validation status."""
    text = _load_report_text(state)
    measurements = extract_measurements(text)
    claim_matrix = _load_claim_matrix(state)
    evidence = _load_evidence(state)
    tables = _table_snapshots(evidence)

    issues: list[dict] = []
    issues.extend(_claim_unit_support_issues(claim_matrix, evidence))
    issues.extend(_claim_table_support_issues(claim_matrix, evidence))
    issues.extend(_unit_notation_issues(measurements))
    issues.extend(_mixed_dimension_unit_issues(measurements))
    issues.extend(_missing_unit_issues(text, measurements))
    calculation_issues, calculation_count = _calculation_issues(text)
    issues.extend(calculation_issues)

    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    info_count = sum(1 for issue in issues if issue.get("severity") == "info")
    report = {
        "job_id": state.job_id,
        "status": "pass" if warning_count == 0 else "review",
        "report_profile": state.spec.get("report_profile", ""),
        "measurement_count": len(measurements),
        "measurements": [item.to_dict() for item in measurements[:100]],
        "table_evidence_count": len(tables),
        "tables": [item.to_dict() for item in tables[:50]],
        "calculation_count": calculation_count,
        "issue_count": len(issues),
        "warning_count": warning_count,
        "info_count": info_count,
        "issues": issues,
    }
    report_path = write_json_artifact(state, "engineering_audit_report.json", report)
    state.qa["engineering_audit_report_path"] = report_path
    report["report_path"] = report_path
    return report
