"""Phase 2 QA node wrappers — adapt standalone functions to state-driven interface.

All Phase 2 QA nodes (consistency_check, style_lint, guideline_check)
are called AFTER CITATION_BIND and BEFORE QA_GATE.
They read from state.drafts paths, write reports to run_dir,
and store paths back into state.qa.

figure_table_plan is called after QA_GATE pass (figures affect render).
research_retrieve triggers re-entry to CLAIM_PLAN if evidence gaps found.
"""
import sys
from pathlib import Path

from ..state import ReportState
from .consistency_check import run_consistency_check
from .style_lint import run_style_lint
from .guideline_check import run_guideline_check
from .figure_table_plan import run_figure_table_plan
from .research_retrieve import run_research_retrieve


def run_consistency_check_wrapper(state: ReportState) -> ReportState:
    """T18: Run all consistency checks. Reads merged_draft + sidecars from state."""
    try:
        merged_path = state.drafts.get("merged_draft_md") or state.drafts.get("merged_draft_path", "")
        sentence_map_path = state.drafts.get("sentence_map_path", "")
        claim_matrix_path = state.plan.get("claim_matrix_path", "")
        figure_manifest_path = state.drafts.get("figure_manifest_path", "")
        tables_path = state.drafts.get("tables_path", "")

        # Resolve run_dir once; Phase 1 writes claim_matrix as dict in state.plan["claim_matrix"]
        run_dir = Path.home() / ".hermes" / "workflow_runs" / state.job_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # claim_matrix: serialize from state.plan dict to file so sub-checks can read it
        claim_matrix = state.plan.get("claim_matrix", {})
        if claim_matrix:
            tmp_path = run_dir / "claim_matrix.json"
            if not tmp_path.exists():
                import json as _json
                with open(tmp_path, "w") as f:
                    _json.dump(claim_matrix, f)
            claim_matrix_path = str(tmp_path)
        if not figure_manifest_path and (run_dir / "figure_manifest.json").exists():
            figure_manifest_path = str(run_dir / "figure_manifest.json")
        if not tables_path and (run_dir / "tables.json").exists():
            tables_path = str(run_dir / "tables.json")

        result = run_consistency_check(
            merged_draft_path=merged_path,
            sentence_sidecar_path=sentence_map_path,
            claim_matrix_path=claim_matrix_path,
            figure_manifest_path=figure_manifest_path,
            tables_path=tables_path,
        )

        # Persist report to run_dir
        report_path = run_dir / "consistency_report.json"
        import json as _json
        with open(report_path, "w") as f:
            _json.dump(result, f, indent=2, default=str)

        # Store in state.qa
        state.qa["consistency_report_path"] = str(report_path)
        state.qa["consistency_gate_status"] = result.get("summary", {}).get("gate_status", "pass")
        state.qa["consistency_status"] = result.get("status", "warning")

    except Exception as e:
        print(f"[WORKFLOW] Node CONSISTENCY_CHECK failed: {type(e).__name__}: {e}", file=sys.stderr)
        # Non-blocking: store empty path, don't raise
        state.qa["consistency_report_path"] = None
        state.qa["consistency_gate_status"] = "pass"
        state.qa["consistency_status"] = "warning"

    return state


def run_style_lint_wrapper(state: ReportState) -> ReportState:
    """T19: Run style lint. WARNING-only gate — never blocks."""
    try:
        merged_path = state.drafts.get("merged_draft_md") or state.drafts.get("merged_draft_path", "")
        blueprint_path = state.plan.get("blueprint_path", "")
        report_family = state.spec.get("report_family", "academic")
        audience = state.spec.get("audience", "expert")

        # Try run_dir for blueprint
        run_dir = Path.home() / ".hermes" / "workflow_runs" / state.job_id
        if not blueprint_path and (run_dir / "blueprint.json").exists():
            blueprint_path = str(run_dir / "blueprint.json")

        result = run_style_lint(
            merged_draft_path=merged_path,
            blueprint_path=blueprint_path,
            report_family=report_family,
            audience=audience,
        )

        # Persist
        report_path = run_dir / "style_report.json"
        import json as _json
        with open(report_path, "w") as f:
            _json.dump(result, f, indent=2, default=str)

        state.qa["style_report_path"] = str(report_path)
        state.qa["style_gate_status"] = result.get("summary", {}).get("gate_status", "warning")
        state.qa["style_status"] = result.get("status", "warning")

    except Exception as e:
        print(f"[WORKFLOW] Node STYLE_LINT failed: {type(e).__name__}: {e}", file=sys.stderr)
        state.qa["style_report_path"] = None
        state.qa["style_gate_status"] = "warning"
        state.qa["style_status"] = "warning"

    return state


def run_guideline_check_wrapper(state: ReportState) -> ReportState:
    """T20: Check report against selected guidelines."""
    try:
        merged_path = state.drafts.get("merged_draft_md") or state.drafts.get("merged_draft_path", "")
        selected_guidelines = state.spec.get("selected_guidelines", [])
        guideline_config_path = state.spec.get("guideline_config_path", "")
        blueprint_path = state.plan.get("blueprint_path", "")
        sentence_map_path = state.drafts.get("sentence_map_path", "")

        run_dir = Path.home() / ".hermes" / "workflow_runs" / state.job_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # guideline_check needs blueprint as file path. blueprint_plan loads from BLUEPRINTS_DIR.
        blueprint = state.plan.get("blueprint", {})
        if blueprint:
            bp_path = run_dir / "blueprint.json"
            if not bp_path.exists():
                import json as _json
                with open(bp_path, "w") as f:
                    _json.dump(blueprint, f)
            blueprint_path = str(bp_path)
        else:
            blueprint_path = str(Path(__file__).parent.parent / "blueprints" / "academic_report.yaml")

        if not guideline_config_path:
            guideline_config_path = str(Path(__file__).parent.parent / "configs" / "guideline_rules.json")
        if not sentence_map_path and (run_dir / "sentence_map.jsonl").exists():
            sentence_map_path = str(run_dir / "sentence_map.jsonl")

        result = run_guideline_check(
            merged_draft_path=merged_path,
            selected_guidelines=selected_guidelines,
            guideline_config_path=guideline_config_path,
            blueprint_path=blueprint_path,
            sentence_map_path=sentence_map_path,
        )

        # Persist
        report_path = run_dir / "guideline_report.json"
        import json as _json
        with open(report_path, "w") as f:
            _json.dump(result, f, indent=2, default=str)

        state.qa["guideline_report_path"] = str(report_path)
        state.qa["guideline_gate_status"] = result.get("summary", {}).get("gate_status", "pass")
        state.qa["guideline_status"] = result.get("status", "warning")

    except Exception as e:
        print(f"[WORKFLOW] Node GUIDELINE_CHECK failed: {type(e).__name__}: {e}", file=sys.stderr)
        state.qa["guideline_report_path"] = None
        state.qa["guideline_gate_status"] = "pass"
        state.qa["guideline_status"] = "warning"

    return state


def run_figure_table_plan_wrapper(state: ReportState) -> ReportState:
    """T21: Plan figures and tables. Runs after QA_GATE pass (non-blocking)."""
    try:
        run_dir = Path.home() / ".hermes" / "workflow_runs" / state.job_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1 writes outline and claim_matrix as dicts in state.plan, not file paths.
        # Serialize to files for figure_table_plan (path-based).
        claim_matrix = state.plan.get("claim_matrix", {})
        claim_matrix_path = ""
        if claim_matrix:
            tmp = run_dir / "claim_matrix.json"
            import json as _json
            with open(tmp, "w") as f:
                _json.dump(claim_matrix, f)
            claim_matrix_path = str(tmp)

        outline = state.plan.get("outline", {})
        outline_path = ""
        if outline:
            tmp = run_dir / "outline.json"
            import json as _json
            with open(tmp, "w") as f:
                _json.dump(outline, f)
            outline_path = str(tmp)

        # evidence_ledger as file path
        evidence_ledger_path = ""
        el = state.sources.get("evidence_ledger", [])
        if el:
            tmp = run_dir / "evidence_ledger.jsonl"
            import json as _json
            with open(tmp, "w") as f:
                for entry in el:
                    f.write(_json.dumps(entry, default=str) + "\n")
            evidence_ledger_path = str(tmp)
        elif (run_dir / "evidence_ledger.jsonl").exists():
            evidence_ledger_path = str(run_dir / "evidence_ledger.jsonl")

        report_family = state.spec.get("report_family", "academic_report")

        result = run_figure_table_plan(
            claim_matrix_path=claim_matrix_path,
            evidence_ledger_path=evidence_ledger_path,
            outline_path=outline_path,
            report_family=report_family,
        )

        state.drafts["figure_manifest_path"] = result.get("figure_manifest_path")
        state.drafts["tables_path"] = result.get("tables_path")
        state.drafts["figure_contract_report_path"] = result.get("figure_contract_report_path")

    except Exception as e:
        print(f"[WORKFLOW] Node FIGURE_TABLE_PLAN failed: {type(e).__name__}: {e}", file=sys.stderr)
        # Non-blocking — figure_table_plan doesn't gate

    return state


def run_research_retrieve_wrapper(state: ReportState) -> ReportState:
    """T22: Retrieve research to fill evidence gaps. May trigger re-entry."""
    try:
        run_dir = Path.home() / ".hermes" / "workflow_runs" / state.job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        report_spec_path = str(run_dir / "report_spec.json")

        # Phase 1 stores claim_matrix as dict in state.plan["claim_matrix"], not file path.
        # Serialize to file if needed.
        claim_matrix = state.plan.get("claim_matrix", {})
        claim_matrix_path = ""
        if claim_matrix:
            tmp = run_dir / "claim_matrix.json"
            import json as _json
            with open(tmp, "w") as f:
                _json.dump(claim_matrix, f)
            claim_matrix_path = str(tmp)
        elif (run_dir / "claim_matrix.json").exists():
            claim_matrix_path = str(run_dir / "claim_matrix.json")

        # evidence_ledger may be stored as list in state.sources["evidence_ledger"].
        el = state.sources.get("evidence_ledger", [])
        evidence_ledger_path = ""
        if el:
            tmp = run_dir / "evidence_ledger.jsonl"
            import json as _json
            with open(tmp, "w") as f:
                for entry in el:
                    f.write(_json.dumps(entry, default=str) + "\n")
            evidence_ledger_path = str(tmp)
        elif (run_dir / "evidence_ledger.jsonl").exists():
            evidence_ledger_path = str(run_dir / "evidence_ledger.jsonl")

        selected_guidelines = state.spec.get("selected_guidelines", [])

        result = run_research_retrieve(
            report_spec_path=report_spec_path,
            claim_matrix_path=claim_matrix_path,
            evidence_ledger_path=evidence_ledger_path,
            selected_guidelines=selected_guidelines,
        )

        # Store paths
        state.sources["research_results_path"] = result.get("research_results_path")
        state.sources["imported_evidence_path"] = result.get("imported_evidence_path")
        state.sources["claim_gap_report_path"] = result.get("claim_gap_report_path")
        state.sources["updated_evidence_ledger_path"] = result.get("updated_evidence_ledger_path")

        # Re-entry flag
        if result.get("requires_claim_replan"):
            state.flags["requires_claim_replan"] = True
        else:
            state.flags["requires_claim_replan"] = False

    except Exception as e:
        print(f"[WORKFLOW] Node RESEARCH_RETRIEVE failed: {type(e).__name__}: {e}", file=sys.stderr)
        state.flags["requires_claim_replan"] = False

    return state
