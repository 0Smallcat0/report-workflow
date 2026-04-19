"""Command line interface for the agent-skill-driven report workflow."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import AgentWorkRequired, QAHardBlockError
from .run_workflow import (
    prepare_workflow,
    render_workflow,
    status_workflow,
    validate_workflow,
    validate_nodes,
)
from .state import ReportState


REPORT_FAMILIES = ("academic_report", "work_report", "hybrid_report")
VALID_ARTIFACT_ROLES = ("source_data", "base_document")


def _parse_source_arg(value: str) -> tuple[str, str]:
    """Parse 'PATH:ROLE' into (path, role). ROLE defaults to 'source_data'.

    Supports both Unix paths (no colons) and Windows paths (with drive letter).
    The role is only extracted when the suffix after the last ':' is a valid role.
    """
    if value.rsplit(":", 1)[-1] in VALID_ARTIFACT_ROLES:
        path, role = value.rsplit(":", 1)
        return path.strip(), role
    return value, "source_data"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="report-workflow")
    subcommands = parser.add_subparsers(dest="command", required=True)

    prepare = subcommands.add_parser("prepare", help="Parse sources and write agent task briefs")
    prepare.add_argument("--prompt", required=True, help="User request for the report")
    prepare.add_argument(
        "--source",
        action="append",
        required=True,
        type=_parse_source_arg,
        help="Source file path; may be repeated. "
             "Format 'PATH:ROLE' to set artifact role (source_data or base_document). "
             "Example: --source data.csv:source_data --source base.docx:base_document",
    )
    prepare.add_argument("--output", required=True, help="Directory for final.docx")
    prepare.add_argument("--family", choices=REPORT_FAMILIES, help="Override inferred report family")
    prepare.add_argument(
        "--intent",
        choices=("new_draft", "revise_existing"),
        default="new_draft",
        help="Task intent (default: new_draft)",
    )

    validate = subcommands.add_parser("validate", help="Validate agent-authored artifacts")
    validate.add_argument("--job-id", required=True, help="Workflow job id from prepare")
    validate.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-node pass/fail results",
    )

    render = subcommands.add_parser("render", help="Render and package a validated workflow")
    render.add_argument("--job-id", required=True, help="Workflow job id")

    status = subcommands.add_parser("status", help="Show current workflow status")
    status.add_argument("--job-id", required=True, help="Workflow job id")

    run = subcommands.add_parser("run", help="Validate and render an existing prepared run")
    run.add_argument("--job-id", required=True, help="Workflow job id with agent artifacts already present")
    run.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-node pass/fail results during validate",
    )

    # Item 6: diff subcommand
    diff = subcommands.add_parser("diff", help="Compare two workflow checkpoints")
    diff.add_argument("--job-id", required=True, help="Base workflow job id")
    diff.add_argument("--against", required=True, help="Workflow job id or checkpoint file to compare against")

    # Item 7: export subcommand
    exp = subcommands.add_parser("export", help="Export full workflow state as JSON")
    exp.add_argument("--job-id", required=True, help="Workflow job id")
    exp.add_argument(
        "--checkpoint",
        help="Checkpoint name to export (default: latest)",
    )
    exp.add_argument(
        "--output",
        help="Output file path (default: stdout)",
    )

    return parser


def _print_state(state) -> None:
    """Print workflow state summary."""
    print(f"job_id: {state.job_id}")
    print(f"status: {state.status}")
    print(f"qa_decision: {state.qa.get('qa_decision', '')}")
    print(f"agent_tasks_dir: {state.runtime.get('agent_tasks_dir', '')}")
    print(f"required_agent_artifacts: {state.runtime.get('required_agent_artifacts', [])}")
    print(f"final_docx_path: {state.output.get('final_docx_path', '')}")
    print(f"published_dir: {state.output.get('published_dir', '')}")


def _verbose_validate(job_id: str) -> ReportState:
    """Run validate with per-node progress printed."""
    state = ReportState.resume(job_id)
    nodes = validate_nodes()
    print(f"[VALIDATE] Running {len(nodes)} nodes for job {job_id} ...")

    for node_name, node_fn in nodes:
        try:
            state = node_fn(state)
            print(f"  [PASS] {node_name}")
        except AgentWorkRequired as exc:
            print(f"  [BLOCK] {node_name} — agent artifacts required: {exc}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {exc}"
            state.runtime["required_agent_artifacts"] = exc.missing_artifacts
            state.status = "awaiting_agent_artifacts"
            raise
        except QAHardBlockError as exc:
            print(f"  [FAIL] {node_name} — {exc}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {exc}"
            state.status = "failed"
            raise
        except Exception as exc:
            print(f"  [ERROR] {node_name} — {type(exc).__name__}: {exc}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {type(exc).__name__}: {exc}"
            state.status = "failed"
            raise

    state.update_status("validated")
    state.checkpoint("VALIDATED")
    print("[VALIDATE] All nodes passed.")
    return state


def _run_diff(base_id: str, against_arg: str) -> int:
    """Compare two checkpoints and print differences."""
    from .state import ReportState, WORKFLOW_RUNS_DIR

    def load_checkpoint(job_id: str) -> dict:
        job_id_clean = job_id.replace(".json", "")
        cp_path = WORKFLOW_RUNS_DIR / job_id_clean / "checkpoint_latest.json"
        if not cp_path.exists():
            cp_path = WORKFLOW_RUNS_DIR / job_id_clean / f"checkpoint_{job_id_clean}.json"
        if not cp_path.exists():
            raise FileNotFoundError(f"No checkpoint found for {job_id}")
        with open(cp_path, encoding="utf-8") as f:
            return json.load(f)

    base = load_checkpoint(base_id)
    other = load_checkpoint(against_arg)

    print(f"--- diff: {base_id} vs {against_arg} ---")
    differences = _compute_diff(base, other)
    if not differences:
        print("No differences found.")
        return 0
    for label, base_val, other_val in differences:
        print(f"\n  [{label}]")
        print(f"    {base_id}: {base_val}")
        print(f"    {against_arg}: {other_val}")
    return 0


def _compute_diff(a: dict, b: dict, path: str = "") -> list[tuple[str, str, str]]:
    """Recursively compute key differences between two state dicts."""
    diffs: list[tuple[str, str, str]] = []
    all_keys = set(a.keys()) | set(b.keys())
    for key in sorted(all_keys):
        cur_path = f"{path}.{key}" if path else key
        if key not in a:
            diffs.append((cur_path, "<missing>", str(b[key])))
        elif key not in b:
            diffs.append((cur_path, str(a[key]), "<missing>"))
        elif a[key] != b[key]:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                diffs.extend(_compute_diff(a[key], b[key], cur_path))
            else:
                diffs.append((cur_path, str(a[key]), str(b[key])))
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare":
            source_files = []
            artifact_role_map: dict[str, str] = {}
            for path, role in args.source:
                source_files.append(str(Path(path)))
                artifact_role_map[str(Path(path).name)] = role

            state = prepare_workflow(
                args.prompt,
                source_files,
                args.output,
                report_family=args.family,
                intent=args.intent,
                artifact_role_map=artifact_role_map,
            )
            _print_state(state)
            return 0

        if args.command == "validate":
            if args.verbose:
                state = _verbose_validate(args.job_id)
            else:
                state = validate_workflow(args.job_id)
            _print_state(state)
            return 0

        if args.command == "render":
            state = render_workflow(args.job_id)
            _print_state(state)
            return 0

        if args.command == "status":
            state = status_workflow(args.job_id)
            _print_state(state)
            return 0

        if args.command == "run":
            if args.verbose:
                state = _verbose_validate(args.job_id)
            else:
                state = validate_workflow(args.job_id)
            state = render_workflow(state.job_id)
            _print_state(state)
            return 0

        if args.command == "diff":
            return _run_diff(args.job_id, args.against)

        if args.command == "export":
            from .state import WORKFLOW_RUNS_DIR
            job_id = args.job_id
            cp_name = args.checkpoint or "checkpoint_latest.json"
            cp_path = WORKFLOW_RUNS_DIR / job_id / cp_name
            if not cp_path.exists():
                # Try as full checkpoint name
                cp_path = WORKFLOW_RUNS_DIR / job_id / f"checkpoint_{args.checkpoint}.json"
            if not cp_path.exists():
                print(f"Checkpoint not found: {cp_path}", file=sys.stderr)
                return 1
            with open(cp_path, encoding="utf-8") as f:
                data = json.load(f)
            output = json.dumps(data, indent=2, default=str)
            if args.output:
                Path(args.output).write_text(output, encoding="utf-8")
                print(f"Exported to {args.output}")
            else:
                print(output)
            return 0

        parser.error(f"unsupported command: {args.command}")
        return 2

    except AgentWorkRequired as exc:
        print(f"report-workflow needs agent artifacts: {exc}", file=sys.stderr)
        if exc.missing_artifacts:
            print("missing_artifacts:", file=sys.stderr)
            for path in exc.missing_artifacts:
                print(f"- {path}", file=sys.stderr)
        return 3
    except QAHardBlockError as exc:
        print(f"report-workflow failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"report-workflow crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
