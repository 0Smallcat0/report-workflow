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
    validate_workflow_dry_run,
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
    prepare.add_argument("--detail", help="Optional report family detail/subtype, e.g. admissions_report")
    prepare.add_argument(
        "--intent",
        choices=("new_draft", "revise_existing"),
        default="new_draft",
        help="Task intent (default: new_draft)",
    )
    prepare.add_argument("--title", help="Structured front matter title")
    prepare.add_argument("--author", help="Structured front matter author block")
    prepare.add_argument("--affiliation", help="Structured front matter affiliation block")
    prepare.add_argument("--correspondence", help="Structured front matter correspondence email/contact")
    prepare.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Structured front matter keyword; may be repeated",
    )
    prepare.add_argument(
        "--project-identity",
        help="Path to project_identity.json with required/forbidden project identity terms",
    )

    validate = subcommands.add_parser("validate", help="Validate agent-authored artifacts")
    validate.add_argument("--job-id", required=True, help="Workflow job id from prepare")
    validate.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-node pass/fail results",
    )
    validate.add_argument(
        "--deep-audit",
        action="store_true",
        help="Enable deep-audit citation substantiveness checking "
             "(verifies evidence content actually supports claim content, not just ID linkage).",
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

    # Item 8: invalidate-cache subcommand - force reload from disk files
    inv = subcommands.add_parser(
        "invalidate-cache",
        help="Clear cached state and force reload from disk files. "
             "Use when you've edited workflow files directly and need to refresh state."
    )
    inv.add_argument("--job-id", required=True, help="Workflow job id")
    inv.add_argument(
        "--sources",
        action="store_true",
        help="Also invalidate cached sources (base_document_sections, evidence_ledger)",
    )
    inv.add_argument(
        "--drafts",
        action="store_true",
        help="Also clear draft paths to force rebuild (MERGE_DRAFT will rebuild from sources)",
    )

    # Item 9: diagnose subcommand - inspect workflow state and find inconsistencies
    diag = subcommands.add_parser(
        "diagnose",
        help="Inspect workflow state, find discrepancies between checkpoint and disk files, "
             "and report revision_plan application status"
    )
    diag.add_argument("--job-id", required=True, help="Workflow job id")
    diag.add_argument(
        "--verbose",
        action="store_true",
        help="Show full checkpoint diff",
    )

    remap = subcommands.add_parser(
        "remap-evidence",
        help="Remap claim, sentence, and section citation evidence IDs from one job to another",
    )
    remap.add_argument("--from-job", required=True, dest="from_job", help="Previous workflow job id")
    remap.add_argument("--to-job", required=True, dest="to_job", help="Current workflow job id")
    remap.add_argument("--write", action="store_true", help="Apply changes instead of dry-run")

    # Item 10: validate with --dry-run option
    validate.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate validation without writing checkpoint. "
             "Use to pre-check before committing changes.",
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


def _verbose_validate(job_id: str, deep_audit: bool = False) -> ReportState:
    """Run validate with per-node progress printed."""
    state = ReportState.resume(job_id)
    if deep_audit:
        state.flags["deep_audit"] = True
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


def _run_invalidate_cache(job_id: str, invalidate_sources: bool, invalidate_drafts: bool) -> int:
    """Clear cached state in checkpoint and optionally force reload from disk."""
    from .state import WORKFLOW_RUNS_DIR

    run_dir = WORKFLOW_RUNS_DIR / job_id
    latest = run_dir / "checkpoint_latest.json"
    if not latest.exists():
        print(f"No checkpoint found for job {job_id}", file=sys.stderr)
        return 1

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    changes = []

    # Clear draft paths to force MERGE_DRAFT rebuild
    if invalidate_drafts:
        drafts = data.get("drafts", {})
        for key in ["merged_draft_md", "publication_draft_md", "merged_draft_cited_md"]:
            if key in drafts:
                changes.append(f"Cleared drafts.{key}")
                del drafts[key]
        data["drafts"] = drafts

    # Clear cached sources to force reload from disk
    if invalidate_sources:
        sources = data.get("sources", {})
        for key in ["base_document_sections"]:
            if key in sources:
                changes.append(f"Cleared sources.{key}")
                del sources[key]
        data["sources"] = sources

    if not changes:
        print("No cache to invalidate. Use --sources or --drafts to specify what to invalidate.")
        return 0

    # Write updated checkpoint
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"Invalidated cache for job {job_id}:")
    for change in changes:
        print(f"  - {change}")
    print("\nNext validate run will reload from disk files.")

    return 0


def _run_diagnose(job_id: str, verbose: bool) -> int:
    """Inspect workflow state and find discrepancies between checkpoint and disk."""
    from .state import WORKFLOW_RUNS_DIR

    run_dir = WORKFLOW_RUNS_DIR / job_id
    latest = run_dir / "checkpoint_latest.json"
    if not latest.exists():
        print(f"No checkpoint found for job {job_id}", file=sys.stderr)
        return 1

    with open(latest, encoding="utf-8") as f:
        data = json.load(f)

    print(f"=== Diagnose: {job_id} ===\n")

    # 1. Checkpoint status
    print(f"Status: {data.get('status', 'unknown')}")
    print(f"qa_decision: {data.get('qa', {}).get('qa_decision', 'none')}")
    print(f"current_node: {data.get('runtime', {}).get('current_node', 'unknown')}")
    print()

    # 2. Check disk files vs checkpoint paths
    drafts = data.get("drafts", {})
    sources = data.get("sources", {})
    issues = []

    print("--- File Existence Checks ---")
    for key, path in drafts.items():
        if path and isinstance(path, str):
            exists = Path(path).exists()
            status = "✓" if exists else "✗ MISSING"
            print(f"  drafts.{key}: {status} ({path})")
            if not exists:
                issues.append(f"drafts.{key} points to missing file: {path}")

    for key in ["base_document_sections_path", "evidence_ledger_path"]:
        path = sources.get(key)
        if path and isinstance(path, str):
            exists = Path(path).exists()
            status = "✓" if exists else "✗ MISSING"
            print(f"  sources.{key}: {status} ({path})")
            if not exists:
                issues.append(f"sources.{key} points to missing file: {path}")
    print()

    # 3. Check if base_document_sections in checkpoint matches disk file
    print("--- Cache Consistency Checks ---")
    disk_base_path = sources.get("base_document_sections_path")
    cached_base = sources.get("base_document_sections", {})
    if disk_base_path and Path(disk_base_path).exists():
        with open(disk_base_path, encoding="utf-8") as f:
            disk_base = json.load(f)
        if cached_base != disk_base:
            print("  ⚠ WARNING: base_document_sections in checkpoint differs from disk file!")
            print(f"    Disk file: {disk_base_path}")
            print(f"    Cache size: {len(str(cached_base))} chars")
            print(f"    Disk size: {len(str(disk_base))} chars")
            issues.append("base_document_sections cache is stale - use 'invalidate-cache --job-id <id> --sources' to refresh")
        else:
            print("  ✓ base_document_sections matches disk file")
    print()

    # 4. Check revision_plan application status
    revision_unapplied = data.get("runtime", {}).get("revision_unapplied", [])
    if revision_unapplied:
        print("--- Revision Plan Issues ---")
        print(f"  {len(revision_unapplied)} change(s) could not be applied:")
        for reason in revision_unapplied:
            print(f"    - {reason}")
        print()
    else:
        print("--- Revision Plan ---")
        print("  ✓ All changes applied successfully")
        print()

    # 5. Check banned phrases in current merged_draft
    merged_path = drafts.get("merged_draft_md")
    if merged_path and Path(merged_path).exists():
        merged_text = Path(merged_path).read_text(encoding="utf-8").lower()
        banned_hints = ["just", "justification", "justified"]
        found_banned = [p for p in banned_hints if p in merged_text]
        if found_banned:
            print("--- Banned Phrase Warning ---")
            print(f"  Found banned phrases: {found_banned}")
            print("    These may cause QA_GATE to fail.")
            print()

    # 6. Citation coverage summary
    sentence_map_path = drafts.get("sentence_map_path")
    if sentence_map_path and Path(sentence_map_path).exists():
        with open(sentence_map_path, encoding="utf-8") as f:
            sents = [json.loads(line) for line in f if line.strip()]
        expected_cites = set()
        for s in sents:
            for cid in s.get("citation_ids", []):
                if cid:
                    expected_cites.add(cid)

        if merged_path and Path(merged_path).exists():
            merged_text = Path(merged_path).read_text(encoding="utf-8")
            present_cites = set()
            import re
            for m in re.findall(r"\[CITE:([^\]]+)\]", merged_text):
                for cid in m.split(","):
                    cid = cid.strip()
                    if cid:
                        present_cites.add(cid)

            missing = expected_cites - present_cites
            if missing:
                print("--- Citation Coverage ---")
                print(f"  Missing citations: {sorted(missing)}")
                print()
            else:
                print("--- Citation Coverage ---")
                print(f"  ✓ All {len(expected_cites)} expected citations present")
                print()

    # 7. Summary
    print("=== Summary ===")
    if issues:
        for issue in issues:
            print(f"  ✗ {issue}")
        print(f"\n{len(issues)} issue(s) found. Run with --verbose for full diff.")
    else:
        print("  ✓ No issues found")

    return 0


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
            project_identity = None
            if args.project_identity:
                with open(args.project_identity, encoding="utf-8") as f:
                    project_identity = json.load(f)

            state = prepare_workflow(
                args.prompt,
                source_files,
                args.output,
                report_family=args.family,
                report_family_detail=args.detail,
                intent=args.intent,
                artifact_role_map=artifact_role_map,
                front_matter={
                    key: value for key, value in {
                        "title": args.title,
                        "author_block": args.author,
                        "affiliation_block": args.affiliation,
                        "correspondence": args.correspondence,
                        "keywords": args.keyword,
                    }.items()
                    if value
                },
                project_identity=project_identity,
            )
            _print_state(state)
            return 0

        if args.command == "validate":
            if args.dry_run:
                state = validate_workflow_dry_run(args.job_id, deep_audit=args.deep_audit)
                _print_state(state)
            elif args.verbose:
                state = _verbose_validate(args.job_id, deep_audit=args.deep_audit)
            else:
                state = validate_workflow(args.job_id, deep_audit=args.deep_audit)
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

        if args.command == "invalidate-cache":
            return _run_invalidate_cache(args.job_id, args.sources, args.drafts)

        if args.command == "diagnose":
            return _run_diagnose(args.job_id, args.verbose)

        if args.command == "remap-evidence":
            from .artifact_contract import remap_evidence_ids
            result = remap_evidence_ids(args.to_job, args.from_job, write=args.write)
            print(json.dumps(result, indent=2, default=str))
            return 0 if result.get("status") == "ok" else 2

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
