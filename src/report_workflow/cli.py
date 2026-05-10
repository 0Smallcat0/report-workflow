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
from .profiles import PROFILE_IDS
from .config import load_config
from .preflight import check_preflight, discover_features
from .preflight_decisions import (
    evaluate_preflight_start,
    pending_preflight_installs,
    required_preflight_decision_shape,
)


REPORT_PROFILES = PROFILE_IDS
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


def _parse_template_field_arg(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Template field must use KEY=VALUE format")
    key, field_value = value.split("=", 1)
    key = key.strip()
    field_value = field_value.strip()
    if not key or not field_value:
        raise argparse.ArgumentTypeError("Template field KEY and VALUE must be non-empty")
    return key, field_value


def _load_preflight_decisions(path: str | None) -> dict | None:
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise argparse.ArgumentTypeError("preflight decisions file must contain a JSON object")
    return data


def _print_preflight_decision_block(
    message: str,
    pending_installs: list[dict],
    ask_user: list[dict],
    decision_issues: list[str] | None = None,
) -> None:
    print(message, file=sys.stderr)
    if decision_issues:
        print("decision_issues:", file=sys.stderr)
        for issue in decision_issues:
            print(f"- {issue}", file=sys.stderr)
    print("required_preflight_decisions:", file=sys.stderr)
    print(
        json.dumps(
            required_preflight_decision_shape(pending_installs, ask_user),
            indent=2,
            default=str,
        ),
        file=sys.stderr,
    )


def _configure_utf8_stdio() -> None:
    """Prefer UTF-8 CLI output on Windows consoles.

    Preflight/status output can contain Chinese prompts and symbols such as
    checkmarks.  Windows cp950 consoles cannot encode all of them, so use
    UTF-8 with replacement fallback when Python exposes reconfigure().
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


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
    prepare.add_argument(
        "--output",
        help="Optional workspace root override. Defaults to repo-local output/",
    )
    prepare.add_argument("--profile", choices=REPORT_PROFILES, help="Override inferred report profile")
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
        "--template-field",
        action="append",
        default=[],
        type=_parse_template_field_arg,
        help="Fixed-template/front-matter field in KEY=VALUE form; may be repeated",
    )
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
    prepare.add_argument(
        "--preflight-decisions",
        help="Path to a JSON preflight_decisions record confirming user install/feature choices",
    )
    prepare.add_argument(
        "--allow-degraded-render",
        action="store_true",
        help="Allow python-docx fallback only when the user accepted degraded rendering in preflight_decisions",
    )
    prepare.add_argument("--enable-research", action="store_true", default=None, help="Enable configured web research")
    prepare.add_argument("--enable-notebook-sync", action="store_true", default=None, help="Enable NotebookLM sync")
    prepare.add_argument("--notebooklm-notebook-id", help="NotebookLM notebook URL or ID for this report")
    prepare.add_argument("--notebooklm-storage-path", help="Optional NotebookLM local storage path")

    validate = subcommands.add_parser("validate", help="Validate agent-authored artifacts")
    validate.add_argument("--job-id", required=True, help="Workflow job id from prepare")
    validate.add_argument("--workspace-root", help="Optional workspace root for locating this run")
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
    render.add_argument("--workspace-root", help="Optional workspace root for locating this run")

    status = subcommands.add_parser("status", help="Show current workflow status")
    status.add_argument("--job-id", required=True, help="Workflow job id")
    status.add_argument("--workspace-root", help="Optional workspace root for locating this run")

    run = subcommands.add_parser("run", help="Validate and render an existing prepared run")
    run.add_argument("--job-id", required=True, help="Workflow job id with agent artifacts already present")
    run.add_argument("--workspace-root", help="Optional workspace root for locating this run")
    run.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-node pass/fail results during validate",
    )

    # Item 6: diff subcommand
    diff = subcommands.add_parser("diff", help="Compare two workflow checkpoints")
    diff.add_argument("--job-id", required=True, help="Base workflow job id")
    diff.add_argument("--against", required=True, help="Workflow job id or checkpoint file to compare against")
    diff.add_argument("--workspace-root", help="Optional workspace root for locating both runs")

    # Item 7: export subcommand
    exp = subcommands.add_parser("export", help="Export full workflow state as JSON")
    exp.add_argument("--job-id", required=True, help="Workflow job id")
    exp.add_argument("--workspace-root", help="Optional workspace root for locating this run")
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
    inv.add_argument("--workspace-root", help="Optional workspace root for locating this run")
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
    diag.add_argument("--workspace-root", help="Optional workspace root for locating this run")
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
    remap.add_argument("--workspace-root", help="Optional workspace root for locating the current run")
    remap.add_argument("--from-workspace-root", help="Optional workspace root for locating the previous run")
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
    print(f"workspace_root: {state.output.get('workspace_root', '')}")
    print(f"run_dir: {state.output.get('run_dir', '')}")
    print(f"final_docx_path: {state.output.get('final_docx_path', '')}")
    print(f"published_dir: {state.output.get('published_dir', '')}")


def _verbose_validate(job_id: str, deep_audit: bool = False, workspace_root: str | None = None) -> ReportState:
    """Run validate with per-node progress printed."""
    state = ReportState.resume(job_id, workspace_root=workspace_root)
    if deep_audit:
        state.flags["deep_audit"] = True
    nodes = validate_nodes()
    print(f"[VALIDATE] Running {len(nodes)} nodes for job {job_id} ...")

    for node_name, node_fn in nodes:
        try:
            state = node_fn(state)
            print(f"  [PASS] {node_name}")
        except AgentWorkRequired as exc:
            print(f"  [BLOCK] {node_name}: agent artifacts required: {exc}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {exc}"
            state.runtime["required_agent_artifacts"] = exc.missing_artifacts
            state.status = "awaiting_agent_artifacts"
            raise
        except QAHardBlockError as exc:
            print(f"  [FAIL] {node_name}: {exc}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {exc}"
            state.status = "failed"
            raise
        except Exception as exc:
            print(f"  [ERROR] {node_name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            state.runtime["error"] = f"{node_name}: {type(exc).__name__}: {exc}"
            state.status = "failed"
            raise

    state.update_status("validated")
    state.checkpoint("VALIDATED")
    print("[VALIDATE] All nodes passed.")
    return state


def _run_diff(base_id: str, against_arg: str, workspace_root: str | None = None) -> int:
    """Compare two checkpoints and print differences."""
    from .state import run_dir_for

    def load_checkpoint(job_id: str) -> dict:
        job_id_clean = job_id.replace(".json", "")
        cp_path = run_dir_for(job_id_clean, workspace_root=workspace_root) / "checkpoint_latest.json"
        if not cp_path.exists():
            cp_path = cp_path.parent / f"checkpoint_{job_id_clean}.json"
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


def _run_invalidate_cache(job_id: str, invalidate_sources: bool, invalidate_drafts: bool, workspace_root: str | None = None) -> int:
    """Clear cached state in checkpoint and optionally force reload from disk."""
    from .state import run_dir_for

    run_dir = run_dir_for(job_id, workspace_root=workspace_root)
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


def _run_diagnose(job_id: str, verbose: bool, workspace_root: str | None = None) -> int:
    """Inspect workflow state and find discrepancies between checkpoint and disk."""
    from .state import run_dir_for

    run_dir = run_dir_for(job_id, workspace_root=workspace_root)
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
            status = "OK" if exists else "MISSING"
            print(f"  drafts.{key}: {status} ({path})")
            if not exists:
                issues.append(f"drafts.{key} points to missing file: {path}")

    for key in ["base_document_sections_path", "evidence_ledger_path"]:
        path = sources.get(key)
        if path and isinstance(path, str):
            exists = Path(path).exists()
            status = "OK" if exists else "MISSING"
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
            print("  WARNING: base_document_sections in checkpoint differs from disk file!")
            print(f"    Disk file: {disk_base_path}")
            print(f"    Cache size: {len(str(cached_base))} chars")
            print(f"    Disk size: {len(str(disk_base))} chars")
            issues.append("base_document_sections cache is stale - use 'invalidate-cache --job-id <id> --sources' to refresh")
        else:
            print("  OK: base_document_sections matches disk file")
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
        print("  OK: all changes applied successfully")
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
                print(f"  OK: all {len(expected_cites)} expected citations present")
                print()

    # 7. Summary
    print("=== Summary ===")
    if issues:
        for issue in issues:
            print(f"  - {issue}")
        print(f"\n{len(issues)} issue(s) found. Run with --verbose for full diff.")
    else:
        print("  OK: no issues found")

    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
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
            template_fields = dict(args.template_field or [])
            cfg = load_config(
                enable_research=args.enable_research,
                enable_notebook_sync=args.enable_notebook_sync,
                notebooklm_notebook_id=args.notebooklm_notebook_id,
                notebooklm_storage_path=args.notebooklm_storage_path,
            )
            preflight = check_preflight()
            discovery = discover_features(
                enable_research=cfg.enable_research,
                enable_notebook_sync=cfg.enable_notebook_sync,
            )
            try:
                preflight_decisions = _load_preflight_decisions(args.preflight_decisions)
            except (OSError, json.JSONDecodeError, argparse.ArgumentTypeError) as exc:
                pending_installs = pending_preflight_installs(preflight, discovery)
                ask_user = discovery.agent_should_ask_user
                _print_preflight_decision_block(
                    "report-workflow prepare requires explicit user preflight decisions.",
                    pending_installs,
                    ask_user,
                    [f"invalid preflight_decisions file: {exc}"],
                )
                return 3

            readiness = evaluate_preflight_start(
                preflight=preflight,
                discovery=discovery,
                cfg=cfg,
                preflight_decisions=preflight_decisions,
                preflight_confirmed=True,
                allow_degraded_render=args.allow_degraded_render,
            )
            if not readiness["ready"]:
                _print_preflight_decision_block(
                    readiness["message"],
                    readiness.get("pending_installs", []),
                    readiness.get("agent_should_ask_user", []),
                    readiness.get("decision_issues", []),
                )
                return 3

            state = prepare_workflow(
                args.prompt,
                source_files,
                args.output,
                report_profile=args.profile,
                intent=args.intent,
                artifact_role_map=artifact_role_map,
                front_matter={
                    key: value for key, value in {
                        "title": args.title,
                        "author_block": args.author,
                        "affiliation_block": args.affiliation,
                        "correspondence": args.correspondence,
                        "keywords": args.keyword,
                        "template_fields": template_fields,
                    }.items()
                    if value
                },
                project_identity=project_identity,
                enable_research=cfg.enable_research,
                enable_notebook_sync=cfg.enable_notebook_sync,
                notebooklm_notebook_id=cfg.notebooklm_notebook_id,
                notebooklm_storage_path=cfg.notebooklm_storage_path,
            )
            _print_state(state)
            return 0

        if args.command == "validate":
            if args.dry_run:
                state = validate_workflow_dry_run(args.job_id, deep_audit=args.deep_audit, workspace_root=args.workspace_root)
                _print_state(state)
            elif args.verbose:
                state = _verbose_validate(args.job_id, deep_audit=args.deep_audit, workspace_root=args.workspace_root)
            else:
                state = validate_workflow(args.job_id, deep_audit=args.deep_audit, workspace_root=args.workspace_root)
            _print_state(state)
            return 0

        if args.command == "render":
            state = render_workflow(args.job_id, workspace_root=args.workspace_root)
            _print_state(state)
            return 0

        if args.command == "status":
            state = status_workflow(args.job_id, workspace_root=args.workspace_root)
            _print_state(state)
            return 0

        if args.command == "run":
            if args.verbose:
                state = _verbose_validate(args.job_id, workspace_root=args.workspace_root)
            else:
                state = validate_workflow(args.job_id, workspace_root=args.workspace_root)
            state = render_workflow(state.job_id, workspace_root=args.workspace_root)
            _print_state(state)
            return 0

        if args.command == "diff":
            return _run_diff(args.job_id, args.against, workspace_root=args.workspace_root)

        if args.command == "invalidate-cache":
            return _run_invalidate_cache(args.job_id, args.sources, args.drafts, workspace_root=args.workspace_root)

        if args.command == "diagnose":
            return _run_diagnose(args.job_id, args.verbose, workspace_root=args.workspace_root)

        if args.command == "remap-evidence":
            from .artifact_contract import remap_evidence_ids
            result = remap_evidence_ids(
                args.to_job,
                args.from_job,
                write=args.write,
                workspace_root=args.workspace_root,
                previous_workspace_root=args.from_workspace_root,
            )
            print(json.dumps(result, indent=2, default=str))
            return 0 if result.get("status") == "ok" else 2

        if args.command == "export":
            from .state import run_dir_for
            job_id = args.job_id
            cp_name = args.checkpoint or "checkpoint_latest.json"
            cp_path = run_dir_for(job_id, workspace_root=args.workspace_root) / cp_name
            if not cp_path.exists():
                # Try as full checkpoint name
                cp_path = run_dir_for(job_id, workspace_root=args.workspace_root) / f"checkpoint_{args.checkpoint}.json"
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
