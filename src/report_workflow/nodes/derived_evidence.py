"""DERIVED_EVIDENCE node — statistics an author asked for, computed here.

The prepare-time summaries cover what every table is asked: how many rows,
what the columns range over, how the categories split. They cannot cover the
figure a particular argument turns on — the median price of one category, the
share of listings under a threshold, the concentration index of a brand
column. Those are specific to the report being written, and there is no way
to know them in advance.

An author registers the request; the value is computed from the rows here.
The author does not supply it. That distinction is the whole design: a
statistic computed privately and typed into a sentence is exactly the
unbacked number the gates exist to catch, and the only way to make it citable
without weakening them is to compute it on this side of the line.

``expect`` is optional, and it is a check rather than an input. When it
disagrees with what the rows produce, the run stops and says both numbers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..derived_evidence import build_requested_units, request_evidence_id
from ..errors import QAHardBlockError
from ..language import CJK_RE
from ..state import ReportState, WORKFLOW_RUNS_DIR

DERIVED_EVIDENCE_FILE = "derived_evidence.json"


def load_requests(run_dir: Path) -> list[dict]:
    """The derivations an author has registered, or an empty list."""
    path = run_dir / DERIVED_EVIDENCE_FILE
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise QAHardBlockError(
            f"{DERIVED_EVIDENCE_FILE} is not readable JSON: {error}"
        ) from error
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rows = payload.get("derivations")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    raise QAHardBlockError(
        f"{DERIVED_EVIDENCE_FILE} must be a list, or an object with a "
        "'derivations' list"
    )


def _read_ledger(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _write_ledger(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")


def apply_derived_evidence(state: ReportState) -> dict:
    """Recompute every registered derivation and refresh the ledger.

    Recomputed rather than trusted, on every run. A ledger line is a file on
    disk; if the only thing standing behind a published figure were the line
    written once at registration time, editing that line would be enough to
    publish anything.
    """
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    requests = load_requests(run_dir)

    ledger_path = Path(
        state.sources.get("evidence_ledger_path") or (run_dir / "evidence_ledger.jsonl")
    )
    existing = _read_ledger(ledger_path)
    units, problems = build_requested_units(
        requests,
        state.sources.get("source_registry", []),
        datetime.now(timezone.utc).isoformat(),
        zh=bool(CJK_RE.search(str(state.spec.get("user_prompt", "")))),
    )

    # The value is recomputed from the rows every run, as above. The timestamp
    # is not a value; regenerating it rewrote every derived line on each run,
    # which moved the ledger hash and hard-blocked the artifacts that had just
    # been stamped against it. Carry the original forward so an unchanged
    # derivation produces an unchanged line.
    first_seen = {
        row.get("evidence_id"): row.get("created_at")
        for row in existing
        if isinstance(row.get("derivation"), dict) and row.get("created_at")
    }
    for unit in units:
        prior = first_seen.get(unit.get("evidence_id"))
        if prior:
            unit["created_at"] = prior

    registered_ids = {
        request_evidence_id(str(request.get("id") or "")) for request in requests
    }
    kept = [
        row
        for row in existing
        if not (
            isinstance(row.get("derivation"), dict)
            and row["derivation"].get("request_id")
        )
        and row.get("evidence_id") not in registered_ids
    ]
    _write_ledger(ledger_path, kept + units)
    state.sources["evidence_ledger_path"] = str(ledger_path)

    report = {
        "requested": len(requests),
        "computed": len(units),
        "problems": problems,
        "evidence": [
            {
                "request_id": unit["derivation"].get("request_id", ""),
                "evidence_id": unit["evidence_id"],
                "method": unit["derivation"].get("method", ""),
                "row_filter": unit["derivation"].get("row_filter", ""),
                "rows_matched": unit["derivation"].get("rows_matched", 0),
                "content": unit["content"],
            }
            for unit in units
        ],
    }
    report_path = run_dir / "derived_evidence_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    state.sources["derived_evidence_report_path"] = str(report_path)
    state.sources["derived_evidence_count"] = len(units)
    return report


def run_derived_evidence(state: ReportState) -> ReportState:
    """Refresh registered derivations before any artifact is validated.

    Runs first in AGENT_ARTIFACTS so a claim citing ``E_D_<id>`` finds that id
    in the ledger when CLAIM_PLAN checks it.
    """
    report = apply_derived_evidence(state)
    if report["problems"]:
        listed = "; ".join(
            f"{problem.get('id') or '<no id>'}: {problem.get('error')}"
            for problem in report["problems"][:5]
        )
        raise QAHardBlockError(
            f"DERIVED_EVIDENCE: {len(report['problems'])} registered derivation(s) "
            f"could not be produced from the source rows: {listed}"
        )
    return state
