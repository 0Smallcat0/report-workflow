"""METHODS_PROTOCOL_BUILD node - split Methods into publication and supplementary.

Sits between SECTION_DRAFT and FIGURE_BUILD in validate phase.

Splits the Methods section into:
1. Publication Methods (methods_protocol.md) - for main document:
   - Corpus/dataset description
   - Graph construction method
   - Node/edge extraction rules
   - Centrality/community detection method
   - Inference confidence handling
   - Validation procedure

2. Supplementary Methods (supplementary_methods.md) - for appendix:
   - Full claim-evidence matrix
   - Internal audit tables
   - Source trace details
   - Extended methodology

Output:
  - methods_protocol.md (for publication)
  - supplementary_methods.md (for appendix)
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..runtime_support import write_json_artifact


def _load_jsonl(path: str | None) -> list[dict]:
    """Load JSONL file."""
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _build_methods_protocol(methods_content: str, evidence_ledger: list[dict]) -> str:
    """Extract publication-ready methods from draft."""
    # Split methods section into paragraphs
    paragraphs = [p.strip() for p in methods_content.split('\n\n') if p.strip()]

    protocol_sections = {
        "corpus_description": [],
        "graph_construction": [],
        "extraction_rules": [],
        "analysis_methods": [],
        "validation": [],
        "other": [],
    }

    # Keywords for classification
    classification_keywords = {
        "corpus_description": ["dataset", "corpus", "source", "collection", "sample", "data source"],
        "graph_construction": ["graph", "node", "edge", "vertices", "links", "construct", "build"],
        "extraction_rules": ["extract", "parse", "identify", "detect", "recognize", "rule"],
        "analysis_methods": ["centrality", "community", "clustering", "detection", "algorithm", "metric"],
        "validation": ["validate", "verify", "evaluate", "assess", "benchmark", "test"],
    }

    for para in paragraphs:
        para_lower = para.lower()
        classified = False

        for category, keywords in classification_keywords.items():
            if any(kw in para_lower for kw in keywords):
                protocol_sections[category].append(para)
                classified = True
                break

        if not classified:
            protocol_sections["other"].append(para)

    # Build protocol document
    protocol = "# Methods\n\n"

    if protocol_sections["corpus_description"]:
        protocol += "## Data Source and Corpus\n\n"
        protocol += "\n\n".join(protocol_sections["corpus_description"]) + "\n\n"

    if protocol_sections["graph_construction"]:
        protocol += "## Graph Construction\n\n"
        protocol += "\n\n".join(protocol_sections["graph_construction"]) + "\n\n"

    if protocol_sections["extraction_rules"]:
        protocol += "## Node and Edge Extraction\n\n"
        protocol += "\n\n".join(protocol_sections["extraction_rules"]) + "\n\n"

    if protocol_sections["analysis_methods"]:
        protocol += "## Analysis Methods\n\n"
        protocol += "\n\n".join(protocol_sections["analysis_methods"]) + "\n\n"

    if protocol_sections["validation"]:
        protocol += "## Validation Procedure\n\n"
        protocol += "\n\n".join(protocol_sections["validation"]) + "\n\n"

    if protocol_sections["other"]:
        protocol += "## Additional Methods\n\n"
        protocol += "\n\n".join(protocol_sections["other"]) + "\n\n"

    return protocol


def _build_supplementary_methods(
    methods_content: str,
    claim_matrix: dict,
    evidence_ledger: list[dict],
    sentence_map: list[dict],
) -> str:
    """Build supplementary methods appendix."""
    supplementary = "# Supplementary Methods\n\n"

    # Claim-Evidence Matrix
    supplementary += "## Claim-Evidence Matrix\n\n"
    supplementary += "| Claim ID | Claim Text | Evidence IDs | Claim Type |\n"
    supplementary += "|-----------|-----------|-------------|-------------|\n"

    for claim in claim_matrix.get("claims", []):
        claim_id = claim.get("claim_id", "")
        claim_text = claim.get("claim_text", "")[:80] + "..." if len(claim.get("claim_text", "")) > 80 else claim.get("claim_text", "")
        evidence_ids = ", ".join(claim.get("evidence_ids", []))
        claim_type = claim.get("claim_type", "")
        supplementary += f"| {claim_id} | {claim_text} | {evidence_ids} | {claim_type} |\n"

    supplementary += "\n\n"

    # Evidence Source Table
    supplementary += "## Evidence Source Table\n\n"
    supplementary += "| Evidence ID | Source File | Source Role | Content Summary |\n"
    supplementary += "|-------------|-------------|-------------|------------------|\n"

    evidence_by_id = {e.get("evidence_id", ""): e for e in evidence_ledger}
    for ev in evidence_ledger:
        eid = ev.get("evidence_id", "")
        fname = ev.get("source_file_name", "")
        role = ev.get("source_role", "")
        content = (ev.get("content", "") or ev.get("claim_text", ""))[:60] + "..."
        supplementary += f"| {eid} | {fname} | {role} | {content} |\n"

    supplementary += "\n\n"

    # Source Trace Details
    supplementary += "## Source Trace Details\n\n"
    supplementary += "### Internal Trace Map\n\n"
    supplementary += "This section preserves the internal mapping between claims, evidence, and source files.\n\n"

    supplementary += "### Evidence Processing Pipeline\n\n"
    supplementary += "| Stage | Description |\n"
    supplementary += "|-------|-------------|\n"
    supplementary += "| Source Parse | Raw source files parsed and content extracted |\n"
    supplementary += "| Evidence Normalize | Content normalized and deduplicated |\n"
    supplementary += "| Claim Extraction | Claims identified and linked to evidence |\n"
    supplementary += "| Sentence Mapping | Individual sentences mapped to claims |\n\n"

    return supplementary


def run_methods_protocol_build(state: ReportState) -> ReportState:
    """T_NEW: METHODS_PROTOCOL_BUILD - split Methods into publication and supplementary.

    Position: After SECTION_DRAFT, before FIGURE_BUILD.
    """
    section_drafts = state.drafts.get("section_drafts", {})
    methods_path = section_drafts.get("methods", "")

    if not methods_path or not Path(methods_path).exists():
        # No methods section to split
        state.drafts["methods_protocol"] = None
        state.drafts["supplementary_methods"] = None
        return state

    with open(methods_path, encoding="utf-8") as f:
        methods_content = f.read()

    # Load supporting data
    evidence_ledger = _load_jsonl(state.sources.get("evidence_ledger_path"))
    claim_matrix = state.plan.get("claim_matrix", {})
    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path"))

    # Build publication methods
    methods_protocol = _build_methods_protocol(methods_content, evidence_ledger)

    # Build supplementary methods
    supplementary_methods = _build_supplementary_methods(
        methods_content, claim_matrix, evidence_ledger, sentence_map
    )

    # Write outputs
    run_dir = WORKFLOW_RUNS_DIR / state.job_id

    methods_protocol_path = run_dir / "methods_protocol.md"
    with open(methods_protocol_path, "w", encoding="utf-8") as f:
        f.write(methods_protocol)

    supplementary_path = run_dir / "supplementary_methods.md"
    with open(supplementary_path, "w", encoding="utf-8") as f:
        f.write(supplementary_methods)

    # Update state - the publication methods will replace the draft methods
    state.drafts["methods_protocol"] = str(methods_protocol_path)
    state.drafts["supplementary_methods"] = str(supplementary_path)

    # Replace the methods draft with the protocol version for publication
    with open(methods_path, "w", encoding="utf-8") as f:
        f.write(methods_protocol)

    return state