"""Read-only linting for agent-authored report artifacts."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact_contract import load_jsonl_without_contract
from .runtime_support import PLACEHOLDER_TEXT, write_json_artifact
from .state import ReportState, run_dir_for


NON_PUBLISHABLE_STATUSES = {"blocked", "unverified", "disputed"}
STRUCTURED_DRAFTS_FILENAME = "structured_drafts.json"


@dataclass
class ArtifactIssue:
    severity: str
    artifact: str
    path: str
    json_path: str
    message: str
    hint: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "artifact": self.artifact,
            "path": self.path,
            "json_path": self.json_path,
            "message": self.message,
            "hint": self.hint,
        }


def _issue(
    issues: list[ArtifactIssue],
    severity: str,
    artifact: str,
    path: Path,
    json_path: str,
    message: str,
    hint: str,
) -> None:
    issues.append(ArtifactIssue(severity, artifact, str(path), json_path, message, hint))


def _load_json(path: Path, artifact: str, issues: list[ArtifactIssue]) -> dict | None:
    if not path.exists():
        _issue(
            issues,
            "error",
            artifact,
            path,
            "$",
            f"{path.name} is missing",
            f"Create {path.name} from the matching agent task brief.",
        )
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _issue(
            issues,
            "error",
            artifact,
            path,
            "$",
            f"Malformed JSON: {exc}",
            "Fix JSON syntax before submitting this artifact.",
        )
        return None
    if not isinstance(payload, dict):
        _issue(
            issues,
            "error",
            artifact,
            path,
            "$",
            f"{path.name} must contain a JSON object",
            "Replace the file root with an object.",
        )
        return None
    return payload


def _load_jsonl(path: Path, artifact: str, issues: list[ArtifactIssue]) -> list[dict]:
    if not path.exists():
        _issue(
            issues,
            "error",
            artifact,
            path,
            "$",
            f"{path.name} is missing",
            "Create sentence_map.jsonl or provide structured_drafts.json so the pipeline can compile it.",
        )
        return []
    try:
        rows = load_jsonl_without_contract(path)
    except json.JSONDecodeError as exc:
        _issue(
            issues,
            "error",
            artifact,
            path,
            "$",
            f"Malformed JSONL: {exc}",
            "Fix the JSON object on the reported line.",
        )
        return []
    except OSError as exc:
        _issue(
            issues,
            "error",
            artifact,
            path,
            "$",
            f"Could not read {path.name}: {exc}",
            "Check that the file exists and is readable.",
        )
        return []
    return rows


def _required_sections(state: ReportState) -> list[str]:
    blueprint = state.plan.get("blueprint") or {}
    sections = blueprint.get("sections") or {}
    section_order = blueprint.get("section_order") or list(sections.keys())
    required: list[str] = []
    for section_id in section_order:
        section = sections.get(section_id, {})
        if isinstance(section, dict) and section.get("required", True) is False:
            continue
        required.append(str(section_id))
    return required


def _known_evidence_from_state(state: ReportState) -> set[str]:
    path = state.sources.get("evidence_ledger_path")
    if not path:
        return set()
    try:
        return {
            str(row.get("evidence_id"))
            for row in load_jsonl_without_contract(path)
            if row.get("evidence_id")
        }
    except Exception:
        return set()


def _lint_claim_matrix(
    state: ReportState,
    run_dir: Path,
    issues: list[ArtifactIssue],
) -> tuple[dict[str, Any] | None, set[str], set[str]]:
    path = run_dir / "claim_matrix.json"
    payload = _load_json(path, "claim_matrix", issues)
    if payload is None:
        return None, set(), set()

    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        _issue(
            issues,
            "error",
            "claim_matrix",
            path,
            "$.claims",
            "claim_matrix.json must contain a non-empty claims list",
            "Add at least one publishable claim with claim_id, claim_text, and evidence_ids.",
        )
        return payload, set(), set()

    seen: set[str] = set()
    claim_ids: set[str] = set()
    claim_evidence: set[str] = set()
    known_evidence = _known_evidence_from_state(state)
    for index, claim in enumerate(claims):
        base = f"$.claims[{index}]"
        if not isinstance(claim, dict):
            _issue(issues, "error", "claim_matrix", path, base, "Claim entry must be an object", "Replace this entry with an object.")
            continue
        claim_id = str(claim.get("claim_id") or "").strip()
        if not claim_id:
            _issue(issues, "error", "claim_matrix", path, f"{base}.claim_id", "Claim is missing claim_id", "Add a stable claim_id such as C001.")
        elif claim_id in seen:
            _issue(issues, "error", "claim_matrix", path, f"{base}.claim_id", f"Duplicate claim_id: {claim_id}", "Rename or merge duplicate claims.")
        else:
            seen.add(claim_id)
            claim_ids.add(claim_id)
        if not str(claim.get("claim_text") or "").strip():
            _issue(issues, "error", "claim_matrix", path, f"{base}.claim_text", "Claim is missing claim_text", "Write a concrete claim sentence.")
        evidence_ids = claim.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            _issue(issues, "error", "claim_matrix", path, f"{base}.evidence_ids", "Claim must include at least one evidence_id", "Use query_evidence to find valid evidence IDs from this run.")
            evidence_ids = []
        for evidence_id in evidence_ids:
            evidence_id = str(evidence_id)
            claim_evidence.add(evidence_id)
            if known_evidence and evidence_id not in known_evidence:
                _issue(
                    issues,
                    "error",
                    "claim_matrix",
                    path,
                    f"{base}.evidence_ids",
                    f"Unknown evidence_id for this run: {evidence_id}",
                    "Use remap_agent_artifacts for reused artifacts, or rebuild from this run's evidence_ledger.jsonl.",
                )
        status = str(claim.get("status") or "supported")
        if status in NON_PUBLISHABLE_STATUSES:
            _issue(
                issues,
                "warning",
                "claim_matrix",
                path,
                f"{base}.status",
                f"Claim status is non-publishable: {status}",
                "Resolve the claim or remove it before publish.",
            )

    return payload, claim_ids, claim_evidence


def _lint_outline(
    state: ReportState,
    run_dir: Path,
    issues: list[ArtifactIssue],
    claim_ids: set[str],
) -> tuple[dict[str, Any] | None, set[str]]:
    path = run_dir / "outline.json"
    payload = _load_json(path, "outline", issues)
    if payload is None:
        return None, set()

    sections = payload.get("sections")
    if not isinstance(sections, dict) or not sections:
        _issue(issues, "error", "outline", path, "$.sections", "outline.json must contain a non-empty sections object", "Add one object per planned report section.")
        return payload, set()

    blueprint_sections = set((state.plan.get("blueprint") or {}).get("sections", {}).keys())
    required_sections = set(_required_sections(state))
    outline_sections = {str(section_id) for section_id in sections.keys()}
    for section_id in sorted(required_sections - outline_sections):
        _issue(
            issues,
            "error",
            "outline",
            path,
            "$.sections",
            f"Missing required section: {section_id}",
            "Add the section required by the active report profile blueprint.",
        )
    for section_id in sorted(outline_sections):
        if blueprint_sections and section_id not in blueprint_sections:
            _issue(issues, "error", "outline", path, f"$.sections.{section_id}", f"Unknown section: {section_id}", "Use section IDs from the selected blueprint.")

    assigned_claims: set[str] = set()
    for section_id, section in sections.items():
        section_path = f"$.sections.{section_id}"
        if not isinstance(section, dict):
            _issue(issues, "error", "outline", path, section_path, "Outline section must be an object", "Replace this section with an object.")
            continue
        raw_claim_ids = section.get("claim_ids", [])
        if not isinstance(raw_claim_ids, list):
            _issue(issues, "error", "outline", path, f"{section_path}.claim_ids", "claim_ids must be a list", "Use an array of claim IDs.")
            continue
        for claim_id in raw_claim_ids:
            claim_id = str(claim_id)
            assigned_claims.add(claim_id)
            if claim_ids and claim_id not in claim_ids:
                _issue(issues, "error", "outline", path, f"{section_path}.claim_ids", f"Unknown claim_id: {claim_id}", "Use claim IDs from claim_matrix.json.")

    for claim_id in sorted(claim_ids - assigned_claims):
        _issue(issues, "error", "outline", path, "$.sections", f"Claim is not assigned to any section: {claim_id}", "Add this claim_id to an appropriate section's claim_ids list.")

    return payload, outline_sections


def _lint_structured_drafts(
    state: ReportState,
    run_dir: Path,
    issues: list[ArtifactIssue],
    claim_ids: set[str],
    claim_evidence: set[str],
    planned_sections: set[str],
) -> bool:
    path = run_dir / STRUCTURED_DRAFTS_FILENAME
    if not path.exists():
        return False
    payload = _load_json(path, "structured_drafts", issues)
    if payload is None:
        return True

    sections = payload.get("sections")
    if isinstance(sections, list):
        normalized = {}
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                _issue(issues, "error", "structured_drafts", path, f"$.sections[{index}]", "Section entry must be an object", "Replace this entry with an object.")
                continue
            section_id = str(section.get("section_id") or "").strip()
            if not section_id:
                _issue(issues, "error", "structured_drafts", path, f"$.sections[{index}].section_id", "Section is missing section_id", "Add a section_id that matches outline.json.")
                continue
            normalized[section_id] = section
        sections = normalized
    if not isinstance(sections, dict) or not sections:
        _issue(issues, "error", "structured_drafts", path, "$.sections", "structured_drafts.json must contain a sections object or list", "Add sections keyed by planned section_id.")
        return True

    for section_id in sorted(planned_sections - {str(key) for key in sections.keys()}):
        _issue(issues, "error", "structured_drafts", path, "$.sections", f"Missing planned section: {section_id}", "Add this section or provide canonical section_drafts/*.md.")

    for section_id, section in sections.items():
        section_path = f"$.sections.{section_id}"
        if not isinstance(section, dict):
            _issue(issues, "error", "structured_drafts", path, section_path, "Section must be an object", "Replace this section with an object.")
            continue
        if planned_sections and str(section_id) not in planned_sections:
            _issue(issues, "warning", "structured_drafts", path, section_path, f"Section is not in outline: {section_id}", "Remove unused sections or add them to outline.json.")
        sentences = section.get("sentences")
        if not isinstance(sentences, list):
            _issue(issues, "error", "structured_drafts", path, f"{section_path}.sentences", "sentences must be a list", "Add sentence objects with text, claim_ids, and evidence_ids.")
            continue
        for sentence_index, sentence in enumerate(sentences):
            base = f"{section_path}.sentences[{sentence_index}]"
            if not isinstance(sentence, dict):
                _issue(issues, "error", "structured_drafts", path, base, "Sentence must be an object", "Replace this entry with an object.")
                continue
            if not str(sentence.get("text") or "").strip():
                _issue(issues, "error", "structured_drafts", path, f"{base}.text", "Sentence is missing text", "Write the sentence text.")
            for field in ("claim_ids", "evidence_ids", "citation_ids"):
                if sentence.get(field) is not None and not isinstance(sentence.get(field), list):
                    _issue(issues, "error", "structured_drafts", path, f"{base}.{field}", f"{field} must be a list", "Use an array, even for one ID.")
            for claim_id in sentence.get("claim_ids") or []:
                if claim_ids and str(claim_id) not in claim_ids:
                    _issue(issues, "error", "structured_drafts", path, f"{base}.claim_ids", f"Unknown claim_id: {claim_id}", "Use claim IDs from claim_matrix.json.")
            for evidence_id in sentence.get("evidence_ids") or []:
                if claim_evidence and str(evidence_id) not in claim_evidence:
                    _issue(issues, "error", "structured_drafts", path, f"{base}.evidence_ids", f"Evidence ID is not declared by claim_matrix: {evidence_id}", "Add the evidence to the linked claim or use the correct evidence_id.")

    return True


def _citation_markers_by_section(section_drafts_dir: Path) -> dict[str, set[str]]:
    markers: dict[str, set[str]] = {}
    if not section_drafts_dir.exists():
        return markers
    for md_path in section_drafts_dir.glob("*.md"):
        text = md_path.read_text(encoding="utf-8")
        found = set()
        for marker in re.findall(r"\[CITE:([^\]]+)\]", text):
            found.update(part.strip() for part in marker.split(",") if part.strip())
        markers[md_path.stem] = found
    return markers


def _lint_canonical_drafts(
    run_dir: Path,
    issues: list[ArtifactIssue],
    claim_ids: set[str],
    claim_evidence: set[str],
    planned_sections: set[str],
) -> None:
    section_drafts_dir = run_dir / "section_drafts"
    sentence_map_path = run_dir / "sentence_map.jsonl"
    if not section_drafts_dir.exists():
        _issue(issues, "error", "section_drafts", section_drafts_dir, "$", "section_drafts directory is missing", "Create section_drafts/*.md or provide structured_drafts.json.")
    else:
        for section_id in sorted(planned_sections):
            draft_path = section_drafts_dir / f"{section_id}.md"
            if not draft_path.exists():
                _issue(issues, "error", "section_drafts", draft_path, "$", f"Missing draft for section: {section_id}", "Create this Markdown draft or use structured_drafts.json.")
                continue
            text = draft_path.read_text(encoding="utf-8")
            if not text.strip():
                _issue(issues, "error", "section_drafts", draft_path, "$", f"Section draft is empty: {section_id}", "Write the section content.")
            if PLACEHOLDER_TEXT in text:
                _issue(issues, "error", "section_drafts", draft_path, "$", f"Section draft contains placeholder text: {section_id}", "Replace placeholder prose with final content.")

    rows = _load_jsonl(sentence_map_path, "sentence_map", issues)
    if not rows:
        return

    markers_by_section = _citation_markers_by_section(section_drafts_dir)
    mapped_evidence_by_section: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        base = f"$[{index}]"
        if not isinstance(row, dict):
            _issue(issues, "error", "sentence_map", sentence_map_path, base, "Row must be an object", "Replace this row with a JSON object.")
            continue
        section_id = str(row.get("section_id") or "").strip()
        if not section_id:
            _issue(issues, "error", "sentence_map", sentence_map_path, f"{base}.section_id", "Row is missing section_id", "Add the section_id for the sentence.")
        elif planned_sections and section_id not in planned_sections:
            _issue(issues, "error", "sentence_map", sentence_map_path, f"{base}.section_id", f"Unknown section_id: {section_id}", "Use a section ID from outline.json.")
        for field in ("claim_ids", "evidence_ids", "citation_ids"):
            if row.get(field) is not None and not isinstance(row.get(field), list):
                _issue(issues, "error", "sentence_map", sentence_map_path, f"{base}.{field}", f"{field} must be a list", "Use an array, even for one ID.")
        for claim_id in row.get("claim_ids") or []:
            if claim_ids and str(claim_id) not in claim_ids:
                _issue(issues, "error", "sentence_map", sentence_map_path, f"{base}.claim_ids", f"Unknown claim_id: {claim_id}", "Use claim IDs from claim_matrix.json.")
        for evidence_id in row.get("evidence_ids") or []:
            if claim_evidence and str(evidence_id) not in claim_evidence:
                _issue(issues, "error", "sentence_map", sentence_map_path, f"{base}.evidence_ids", f"Evidence ID is not declared by claim_matrix: {evidence_id}", "Add this evidence to the linked claim or use the correct evidence_id.")
            if section_id:
                mapped_evidence_by_section.setdefault(section_id, set()).add(str(evidence_id))

    for section_id, mapped_ids in mapped_evidence_by_section.items():
        marker_ids = markers_by_section.get(section_id, set())
        missing_markers = sorted(mapped_ids - marker_ids)
        if missing_markers:
            _issue(
                issues,
                "warning",
                "section_drafts",
                section_drafts_dir / f"{section_id}.md",
                "$",
                "sentence_map evidence_ids are missing from [CITE:] markers: " + ", ".join(missing_markers[:12]),
                "Add matching [CITE:<evidence_id>] markers, or author with structured_drafts.json.",
            )


def _lint_revision_plan(run_dir: Path, issues: list[ArtifactIssue]) -> None:
    path = run_dir / "revision_plan.json"
    payload = _load_json(path, "revision_plan", issues)
    if payload is None:
        return
    changes = payload.get("changes")
    if not isinstance(changes, list) or not changes:
        _issue(issues, "error", "revision_plan", path, "$.changes", "revision_plan.json must contain a non-empty changes list", "Add replacement or insertion changes against the base document.")


def lint_agent_artifacts(state: ReportState) -> dict[str, Any]:
    """Lint agent-owned artifacts and write artifact_lint_report.json."""
    run_dir = run_dir_for(state)
    issues: list[ArtifactIssue] = []
    claim_matrix, claim_ids, claim_evidence = _lint_claim_matrix(state, run_dir, issues)
    _outline, outline_sections = _lint_outline(state, run_dir, issues, claim_ids)
    planned_sections = outline_sections or set(_required_sections(state))

    if state.spec.get("task_intent") == "revise_existing":
        _lint_revision_plan(run_dir, issues)
    else:
        used_structured = _lint_structured_drafts(
            state,
            run_dir,
            issues,
            claim_ids,
            claim_evidence,
            planned_sections,
        )
        if not used_structured:
            _lint_canonical_drafts(run_dir, issues, claim_ids, claim_evidence, planned_sections)

    issue_dicts = [issue.to_dict() for issue in issues]
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    report = {
        "job_id": state.job_id,
        "status": "pass" if error_count == 0 else "fail",
        "task_intent": state.spec.get("task_intent", "new_draft"),
        "claim_count": len((claim_matrix or {}).get("claims", [])) if isinstance(claim_matrix, dict) else 0,
        "issue_count": len(issues),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issue_dicts,
    }
    report_path = write_json_artifact(state, "artifact_lint_report.json", report)
    report["report_path"] = report_path
    return report
