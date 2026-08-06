"""SOURCE_APPENDIX_RENDER node - render internal source appendix as separate traceability document.

Sits between PUBLICATION_STYLE_PASS and FINAL_PUBLISH in the render phase.

The internal_source_appendix.md contains [Source: ...] markers stripped from
body prose, organized as a traceability log. It is NOT part of the published
report — it is published as a separate traceability_appendix.docx.

Output: traceability_appendix.docx
"""
from pathlib import Path
import json

from ..state import ReportState, WORKFLOW_RUNS_DIR
from .docx_render import markdown_to_docx


def _load_jsonl(path: str) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _structured_traceability_markdown(state: ReportState) -> str:
    """Build a readable internal appendix from trace map sidecars."""
    trace_path = state.citations.get("internal_trace_path", "")
    if not trace_path or not Path(trace_path).exists():
        return ""

    with open(trace_path, encoding="utf-8") as f:
        trace = json.load(f)

    evidence_by_id = {
        evidence.get("evidence_id"): evidence
        for evidence in _load_jsonl(state.sources.get("evidence_ledger_path", ""))
        if evidence.get("evidence_id")
    }

    claims = trace.get("claims", [])
    if not claims:
        return ""

    by_source: dict[tuple[str, str], dict] = {}
    for claim in claims:
        claim_id = claim.get("claim_id", "")
        claim_text = claim.get("claim_text", "")
        for evidence_id in claim.get("evidence_ids", []):
            evidence = evidence_by_id.get(evidence_id, {})
            source = evidence.get("source_file_name") or evidence.get("source_id") or "unknown source"
            role = evidence.get("source_role", "unknown")
            key = (source, role)
            entry = by_source.setdefault(key, {"evidence_ids": set(), "claims": []})
            entry["evidence_ids"].add(evidence_id)
            entry["claims"].append({
                "claim_id": claim_id,
                "claim_text": claim_text,
                "evidence_id": evidence_id,
            })

    lines = [
        "# Internal Traceability Appendix",
        "",
        "This appendix maps report claims to evidence sidecars. It is for audit use and is not part of the publication text.",
        "",
    ]

    for (source, role), entry in sorted(by_source.items()):
        evidence_ids = sorted(entry["evidence_ids"])
        lines.extend([
            f"## Source: {source}",
            "",
            f"- Source role: {role}",
            f"- Evidence IDs: {', '.join(evidence_ids)}",
            "- Mapping: the evidence entries listed above support the claims below through `claim_matrix.json` and `sentence_map.jsonl`.",
            "",
        ])
        seen_claims = set()
        for claim in entry["claims"]:
            key = (claim["claim_id"], claim["evidence_id"])
            if key in seen_claims:
                continue
            seen_claims.add(key)
            claim_text = " ".join(str(claim["claim_text"]).split())
            if len(claim_text) > 220:
                claim_text = claim_text[:217].rstrip() + "..."
            lines.append(f"- {claim['claim_id']} via {claim['evidence_id']}: {claim_text}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _record_absence(state: ReportState, detail: str) -> None:
    """No appendix. Say whether that is expected or a defect.

    These two cases used to return the same empty string. A run whose sources
    genuinely cite nobody and a run that read thirty-nine citations and
    extracted none of them both ended here silently, so the second one — a
    real defect, and the one that emptied the deliverable's bibliography —
    looked exactly like the first and nothing anywhere raised a word about it.
    """
    state.output["traceability_appendix_docx_path"] = ""
    state.output["traceability_appendix_status"] = "absent"

    cited_count = int(state.sources.get("cited_source_count", 0) or 0)
    claim_count = len((state.plan.get("claim_matrix") or {}).get("claims", []) or [])
    if cited_count or claim_count:
        state.output["traceability_appendix_status"] = "missing"
        state.runtime.setdefault("warnings", []).append(
            f"SOURCE_APPENDIX_RENDER produced no appendix although this run has "
            f"{cited_count} cited source(s) and {claim_count} claim(s): {detail}. "
            "The delivered document will carry no traceability appendix."
        )


def run_source_appendix_render(state: ReportState) -> ReportState:
    """T_NEW: SOURCE_APPENDIX_RENDER - render source appendix as separate docx.

    Position: After PUBLICATION_STYLE_PASS, before FINAL_PUBLISH.
    """
    source_appendix_path = state.citations.get("internal_source_appendix_path", "")
    trace_path = state.citations.get("internal_trace_path", "")
    if (
        (not source_appendix_path or not Path(source_appendix_path).exists())
        and (not trace_path or not Path(trace_path).exists())
    ):
        _record_absence(state, "no traceability inputs were produced")
        return state

    appendix_md = _structured_traceability_markdown(state)
    if not appendix_md and source_appendix_path and Path(source_appendix_path).exists():
        appendix_md = Path(source_appendix_path).read_text(encoding="utf-8")
    if not appendix_md.strip():
        _record_absence(state, "traceability inputs produced no appendix content")
        return state

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    appendix_docx_path = run_dir / "traceability_appendix.docx"

    try:
        markdown_to_docx(appendix_md, str(appendix_docx_path))
    except Exception as exc:
        # Don't hard-fail the whole render if appendix fails
        state.output["traceability_appendix_docx_path"] = ""
        state.runtime["warning"] = f"SOURCE_APPENDIX_RENDER failed: {exc}"
        return state

    state.output["traceability_appendix_docx_path"] = str(appendix_docx_path)
    return state
