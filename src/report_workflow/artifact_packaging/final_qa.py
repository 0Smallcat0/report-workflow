"""Final delivery QA summary packaging."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..state import ReportState
from .common import existing_path, file_size, load_json, write_json, write_text


def _check_status(payload: dict, issue_count: int = 0) -> str:
    if not payload:
        return "missing"
    status = str(payload.get("status") or "").lower()
    if status in {"failed", "fail", "validation_failed"}:
        return "failed"
    if issue_count > 0 or status in {"review_recommended", "issues_found", "warning"}:
        return "review"
    if status in {"ok", "passed", "pass"} or not status:
        return "pass"
    return status


def _count_issues(payload: dict) -> int:
    issues = payload.get("issues", [])
    return len(issues) if isinstance(issues, list) else 0


def _render_issue_list(*reports: dict) -> list[str]:
    issues: list[str] = []
    for report in reports:
        raw = report.get("issues", [])
        if isinstance(raw, list):
            issues.extend(str(item) for item in raw)
    return issues


def _build_final_qa_summary_md(summary: dict) -> str:
    gate = summary["gate_summary"]
    factuality = summary["factuality"]
    lint = summary["artifact_lint"]
    engineering = summary["engineering_audit"]
    scholarly = summary["scholarly_quality"]
    template_style = summary["template_style"]
    template_fields = summary["template_field_fill"]
    figure_visual = summary["figure_visual_quality"]
    render = summary["render"]
    report = summary["report"]

    lines = [
        "# Final QA Summary",
        "",
        f"- Overall status: {summary['overall_status']}",
        f"- QA decision: {gate['qa_decision'] or 'unknown'}",
        f"- Report profile: {summary['report_profile'] or 'unknown'}",
        f"- Renderer: {report['renderer_used'] or 'unknown'}",
        f"- Final DOCX: {report['final_docx_path'] or 'missing'}",
        "",
        "## Key Checks",
        "",
        (
            f"- Factuality: {factuality['status']} "
            f"({factuality['verified_count']} verified, {factuality['blocked_count']} blocked)"
        ),
        (
            f"- Artifact lint: {lint['status']} "
            f"({lint['error_count']} errors, {lint['warning_count']} warnings)"
        ),
        (
            f"- Engineering audit: {engineering['status']} "
            f"({engineering['warning_count']} warnings, {engineering['table_evidence_count']} table evidence units)"
        ),
        (
            f"- Scholarly quality: {scholarly['status']} "
            f"({scholarly['issue_count']} issues, {scholarly['hard_issue_count']} hard)"
        ),
        (
            f"- Template style: {template_style['status']} "
            f"({template_style['warning_count']} warnings, "
            f"reference applied: {template_style['reference_docx_applied']})"
        ),
        (
            f"- Template fields: {template_fields['status']} "
            f"({template_fields['filled_count']} filled, {template_fields['warning_count']} warnings)"
        ),
        (
            f"- Figure visual quality: {figure_visual['status']} "
            f"({figure_visual['issue_count']} review issues across {figure_visual['figure_count']} figures)"
        ),
        (
            f"- Render: {render['status']} "
            f"({render['paragraph_count']} paragraphs, {render['table_count']} tables, "
            f"{render['inline_shape_count']} inline shapes)"
        ),
        "",
        "## Packaged Evidence",
        "",
    ]
    for label, path in summary["source_artifacts"].items():
        lines.append(f"- {label}: {path or 'missing'}")

    if gate["hard_fail_reasons"]:
        lines.extend(["", "## Hard Fail Reasons", ""])
        lines.extend(f"- {reason}" for reason in gate["hard_fail_reasons"])

    if render["issues"]:
        lines.extend(["", "## Render Issues", ""])
        lines.extend(f"- {issue}" for issue in render["issues"])

    lines.append("")
    return "\n".join(lines)


def build_final_qa_summary(state: ReportState, run_dir: Path) -> dict[str, str]:
    layout_manifest_path = (
        state.runtime.get("post_render_layout_manifest_path")
        or state.output.get("post_render_layout_manifest_path")
    )
    artifact_lint_path = run_dir / "artifact_lint_report.json"
    artifact_lint_path_str = str(artifact_lint_path) if artifact_lint_path.exists() else ""

    qa_summary = load_json(state.qa.get("qa_summary_path"))
    factuality = load_json(state.qa.get("factuality_report_path"))
    engineering = load_json(state.qa.get("engineering_audit_report_path"))
    lint = load_json(artifact_lint_path_str)
    template_style_map = load_json(state.output.get("template_style_map_path"))
    template_field_fill = load_json(state.output.get("template_field_fill_report_path"))
    post_render_validate = load_json(state.runtime.get("post_render_validate_report_path"))
    layout = load_json(layout_manifest_path)
    visual = load_json(state.runtime.get("visual_render_check_report_path"))
    figure_visual_path = (
        state.qa.get("figure_visual_quality_report_path")
        or state.output.get("figure_visual_quality_report_path")
    )
    figure_visual = load_json(figure_visual_path)
    scholarly_path = (
        state.qa.get("scholarly_quality_report_path")
        or state.output.get("scholarly_quality_report_path")
    )
    scholarly = load_json(scholarly_path)

    hard_fail_reasons = state.qa.get("hard_fail_reasons", [])
    citation_audit = state.citations.get("citation_audit", [])
    unresolved_citations = [
        item for item in citation_audit
        if isinstance(item, dict) and item.get("resolved") is False
    ]

    render_issues = _render_issue_list(post_render_validate, layout, visual)
    render_counts = layout.get("counts", {}) if isinstance(layout.get("counts"), dict) else {}
    render_status = "failed" if (
        _check_status(post_render_validate) == "failed"
        or _check_status(layout) == "failed"
        or _check_status(visual) == "failed"
    ) else ("review" if render_issues else "pass")

    factuality_blocked = int(factuality.get("blocked_count", 0) or 0)
    factuality_verified = int(factuality.get("verified_count", 0) or 0)
    lint_error_count = int(lint.get("error_count", 0) or 0)
    lint_warning_count = int(lint.get("warning_count", 0) or 0)
    engineering_warning_count = int(engineering.get("warning_count", 0) or 0)
    engineering_issue_count = int(engineering.get("issue_count", 0) or 0)
    template_style_warning_count = len(template_style_map.get("warnings", [])) if template_style_map else 0
    template_field_warning_count = len(template_field_fill.get("warnings", [])) if template_field_fill else 0
    figure_visual_issue_count = int(figure_visual.get("issue_count", 0) or 0)
    scholarly_issue_count = int(scholarly.get("issue_count", 0) or 0)
    scholarly_hard_issue_count = int(scholarly.get("hard_issue_count", 0) or 0)

    failed = (
        state.qa.get("qa_decision") not in ("pass", None, "")
        or bool(hard_fail_reasons)
        or factuality_blocked > 0
        or lint_error_count > 0
        or scholarly_hard_issue_count > 0
        or render_status == "failed"
    )
    needs_review = (
        lint_warning_count > 0
        or engineering_warning_count > 0
        or engineering_issue_count > 0
        or template_style_warning_count > 0
        or template_field_warning_count > 0
        or figure_visual_issue_count > 0
        or scholarly_issue_count > 0
        or render_status == "review"
    )
    overall_status = "failed" if failed else ("review" if needs_review else "pass")

    docx_path = state.output.get("final_docx_path") or state.output.get("rendered_docx_path", "")
    summary = {
        "job_id": state.job_id,
        "created_at": datetime.now().isoformat(),
        "status": state.status,
        "overall_status": overall_status,
        "report_profile": state.spec.get("report_profile", ""),
        "report": {
            "final_docx_path": existing_path(docx_path),
            "published_report_path": existing_path(state.output.get("published_report_path")),
            "renderer_used": state.output.get("renderer_used", ""),
            "file_size_bytes": file_size(docx_path),
            "workflow_success": bool(state.output.get("workflow_success") and state.status == "completed"),
        },
        "gate_summary": {
            "qa_decision": state.qa.get("qa_decision", ""),
            "artifact_completeness_status": state.qa.get("artifact_completeness_status", ""),
            "hard_fail_count": len(hard_fail_reasons),
            "hard_fail_reasons": hard_fail_reasons,
            "citation_audit_count": len(citation_audit) if isinstance(citation_audit, list) else 0,
            "unresolved_citation_count": len(unresolved_citations),
        },
        "factuality": {
            "status": "missing" if not factuality else ("failed" if factuality_blocked else "pass"),
            "verified_count": factuality_verified,
            "blocked_count": factuality_blocked,
            "claim_count": len(factuality.get("claims", [])) if isinstance(factuality.get("claims"), list) else 0,
            "path": existing_path(state.qa.get("factuality_report_path")),
        },
        "artifact_lint": {
            "status": _check_status(lint, lint_error_count + lint_warning_count),
            "error_count": lint_error_count,
            "warning_count": lint_warning_count,
            "issue_count": _count_issues(lint),
            "path": existing_path(artifact_lint_path_str),
        },
        "engineering_audit": {
            "status": _check_status(engineering, engineering_issue_count),
            "warning_count": engineering_warning_count,
            "issue_count": engineering_issue_count,
            "info_count": int(engineering.get("info_count", 0) or 0),
            "measurement_count": int(engineering.get("measurement_count", 0) or 0),
            "table_evidence_count": int(engineering.get("table_evidence_count", 0) or 0),
            "calculation_count": int(engineering.get("calculation_count", 0) or 0),
            "path": existing_path(state.qa.get("engineering_audit_report_path")),
        },
        "scholarly_quality": {
            "status": _check_status(scholarly, scholarly_issue_count),
            "issue_count": scholarly_issue_count,
            "hard_issue_count": scholarly_hard_issue_count,
            "review_issue_count": int(scholarly.get("review_issue_count", 0) or 0),
            "path": existing_path(scholarly_path),
        },
        "template_style": {
            "status": _check_status(template_style_map, template_style_warning_count),
            "warning_count": template_style_warning_count,
            "reference_template_mode": template_style_map.get("reference_template_mode", ""),
            "renderer_used": template_style_map.get("renderer_used", ""),
            "reference_docx_applied": bool(template_style_map.get("reference_docx_applied")),
            "rendered_paragraph_style_count": (
                template_style_map.get("style_comparison", {}).get("rendered_paragraph_style_count", 0)
                if isinstance(template_style_map.get("style_comparison"), dict)
                else 0
            ),
            "path": existing_path(state.output.get("template_style_map_path")),
        },
        "template_field_fill": {
            "status": _check_status(template_field_fill, template_field_warning_count),
            "warning_count": template_field_warning_count,
            "field_count": int(template_field_fill.get("field_count", 0) or 0),
            "filled_count": int(template_field_fill.get("filled_count", 0) or 0),
            "missing_value_count": int(template_field_fill.get("missing_value_count", 0) or 0),
            "not_found_count": int(template_field_fill.get("not_found_count", 0) or 0),
            "path": existing_path(state.output.get("template_field_fill_report_path")),
        },
        "figure_visual_quality": {
            "status": _check_status(figure_visual, figure_visual_issue_count),
            "issue_count": figure_visual_issue_count,
            "figure_count": len(figure_visual.get("figures", [])) if isinstance(figure_visual.get("figures"), list) else 0,
            "path": existing_path(figure_visual_path),
        },
        "render": {
            "status": render_status,
            "post_render_validate_status": post_render_validate.get("status", "missing") if post_render_validate else "missing",
            "layout_manifest_status": layout.get("status", "missing") if layout else "missing",
            "visual_render_status": visual.get("status", "missing") if visual else "missing",
            "paragraph_count": int(render_counts.get("paragraphs", post_render_validate.get("paragraph_count", 0)) or 0),
            "table_count": int(render_counts.get("tables", post_render_validate.get("table_count", 0)) or 0),
            "inline_shape_count": int(render_counts.get("inline_shapes", post_render_validate.get("inline_shape_count", 0)) or 0),
            "issues": render_issues,
            "post_render_layout_manifest_path": existing_path(layout_manifest_path),
        },
        "source_artifacts": {
            "qa_summary": existing_path(state.qa.get("qa_summary_path")),
            "factuality_report": existing_path(state.qa.get("factuality_report_path")),
            "artifact_lint_report": existing_path(artifact_lint_path_str),
            "engineering_audit_report": existing_path(state.qa.get("engineering_audit_report_path")),
            "scholarly_quality_report": existing_path(scholarly_path),
            "scholarly_quality_report_md": existing_path(state.qa.get("scholarly_quality_report_md_path")),
            "template_style_map": existing_path(state.output.get("template_style_map_path")),
            "template_field_fill_report": existing_path(state.output.get("template_field_fill_report_path")),
            "figure_visual_quality_report": existing_path(figure_visual_path),
            "post_render_validate_report": existing_path(state.runtime.get("post_render_validate_report_path")),
            "post_render_layout_manifest": existing_path(layout_manifest_path),
            "visual_render_check_report": existing_path(state.runtime.get("visual_render_check_report_path")),
        },
        "qa_summary": qa_summary,
    }

    json_path = run_dir / "final_qa_summary.json"
    md_path = run_dir / "final_qa_summary.md"
    write_json(json_path, summary)
    write_text(md_path, _build_final_qa_summary_md(summary))
    state.qa["final_qa_summary_path"] = str(json_path)
    state.qa["final_qa_summary_md_path"] = str(md_path)
    state.output["final_qa_summary_path"] = str(json_path)
    state.output["final_qa_summary_md_path"] = str(md_path)
    return {"json": str(json_path), "markdown": str(md_path)}
