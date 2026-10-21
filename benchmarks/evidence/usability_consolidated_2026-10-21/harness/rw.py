"""Drive one report through the controlled harness, one step per call.

    python harness/rw.py <report_dir> start            # check_environment + start_report
    python harness/rw.py <report_dir> next             # get_next_action
    python harness/rw.py <report_dir> put              # copy authored/ files the stage may write
    python harness/rw.py <report_dir> submit           # submit_action
    python harness/rw.py <report_dir> register <file>  # register_derived_evidence
    python harness/rw.py <report_dir> publish          # publish_report

Runs go to $RW_RUNS (default: <report_dir>/../.runs, git-ignored). Every call is
appended to <report_dir>/logs/$RW_LABEL.jsonl with the status and message, and
no machine path is written to the log.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from report_workflow import agent_wrapper as aw

HERE = Path(__file__).resolve().parent


def _scrub(value, roots):
    if isinstance(value, str):
        for root in roots:
            value = value.replace(str(root), "<run>" if root.name != "sources" else "<sources>")
        return value
    if isinstance(value, dict):
        return {k: _scrub(v, roots) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, roots) for v in value]
    return value


def _answer_template(template: dict) -> dict:
    """Fill the preflight template the way an agent does: skip whatever it asks."""
    filled = json.loads(json.dumps(template))
    for group in ("install_decisions", "feature_decisions"):
        for key, value in list((filled.get(group) or {}).items()):
            if isinstance(value, str) and "|" in value:
                filled[group][key] = "skip"
    return filled


def _ledger_ids(run_dir: Path) -> dict[str, str]:
    """First line of every intake table's text -> its evidence id in this run."""
    found = {}
    for line in (run_dir / "evidence_ledger.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("table_grid"):
            found[str(row.get("content", "")).splitlines()[0]] = row["evidence_id"]
    return found


def _remap(text: str, report: Path, run_dir: Path) -> str:
    """Intake table ids are digests of their text; a version that words the
    table differently gives it another id. Map the author's ids by the table's
    first line, recorded once in authored/id_labels.json."""
    labels = report / "authored" / "id_labels.json"
    if not labels.is_file():
        return text
    here = _ledger_ids(run_dir)
    for old_id, first_line in json.loads(labels.read_text(encoding="utf-8")).items():
        new_id = next((eid for line, eid in here.items() if line.split("。")[0] == first_line.split("。")[0]), None)
        if new_id:
            text = text.replace(old_id, new_id)
    return text


def main() -> int:
    report = Path(sys.argv[1]).resolve()
    command = sys.argv[2]
    label = os.environ.get("RW_LABEL", "branch")
    runs = Path(os.environ.get("RW_RUNS", HERE.parent / ".runs")) / f"{report.name}-{label}"
    state_file = runs / "job.json"
    job = json.loads(state_file.read_text())["job_id"] if state_file.exists() else None
    ws = str(runs / "out")
    result: dict
    if command == "start":
        if runs.exists():
            shutil.rmtree(runs)
        runs.mkdir(parents=True)
        env = aw.check_environment()
        spec = json.loads((report / "authored" / "start.json").read_text(encoding="utf-8"))
        spec["source_files"] = [
            {**entry, "path": str(report / "sources" / entry["path"])} for entry in spec["source_files"]
        ]
        result = aw.start_report(
            output_dir=str(runs / "out"),
            preflight_confirmed=True,
            preflight_decisions=_answer_template(env["required_preflight_decisions"]),
            **spec,
        )
        state_file.write_text(json.dumps({"job_id": result.get("job_id")}))
    elif command == "next":
        result = aw.get_next_action(job_id=job, workspace_root=ws)
    elif command == "put":
        action = aw.get_next_action(job_id=job, workspace_root=ws)
        copied = []
        for target in action.get("allowed_write_paths") or []:
            name = Path(target).name
            edit = report / "authored" / "figure_plan_edit.json"
            if name == "figure_plan.json" and edit.is_file() and Path(target).is_file():
                # Keep the starter figures the author chose, with the author's
                # titles; the plotted data stays the pipeline's.
                keep = json.loads(edit.read_text(encoding="utf-8"))["keep"]
                plan = json.loads(Path(target).read_text(encoding="utf-8"))
                plan["figures"] = [
                    {**figure, **keep[str(figure.get("figure_id"))]}
                    for figure in plan.get("figures", [])
                    if str(figure.get("figure_id")) in keep
                ]
                Path(target).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
                copied.append("figure_plan.json (edited)")
                continue
            source = report / "authored" / name
            if source.is_file():
                run_dir = Path(target).parent if name != "figure_plan.json" else Path(target).parent.parent
                raw = _remap(source.read_text(encoding="utf-8"), report, run_dir)
                data = json.loads(raw) if name.endswith(".json") else None
                existing = Path(target)
                if data is not None:
                    try:
                        contract = json.loads(existing.read_text(encoding="utf-8")).get("_contract") if existing.is_file() else None
                    except (ValueError, AttributeError):
                        contract = None
                    if contract and isinstance(data, dict):
                        data = {"_contract": contract, **{k: v for k, v in data.items() if k != "_contract"}}
                    Path(target).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                else:
                    Path(target).write_text(raw, encoding="utf-8")
                copied.append(name)
        result = {"status": "copied", "files": copied, "stage": action.get("stage")}
    elif command == "submit":
        result = aw.submit_action(job_id=job, workspace_root=ws)
    elif command == "register":
        derivations = json.loads((report / "authored" / sys.argv[3]).read_text(encoding="utf-8"))
        # (registrations name files and columns, not intake ids)
        result = aw.register_derived_evidence(job_id=job, derivations=derivations, workspace_root=ws)
    elif command == "publish":
        result = aw.publish_report(job_id=job, workspace_root=ws)
    else:
        raise SystemExit(f"unknown command {command}")
    roots = [runs, report / "sources"]
    record = {"step": command, "job_id": job or result.get("job_id")}
    for key in ("status", "stage", "message", "error_details", "problems", "docx_path", "repair_context"):
        if key in result and result[key]:
            record[key] = result[key]
    record = _scrub(record, roots)
    log = report / "logs" / f"{label}.jsonl"
    log.parent.mkdir(exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(_scrub(result, []), ensure_ascii=False, indent=1, default=str)[:20000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
