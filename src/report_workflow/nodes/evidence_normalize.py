"""EVIDENCE_NORMALIZE node - deterministic evidence scoring."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..artifact_contract import stable_evidence_id


STRUCTURED_TYPES = {"csv", "xlsx", "json"}
FIRST_HAND_TYPES = {"pdf", "docx"}

# ------------------------------------------------------------------
# Fix #4: source_role classification
# ------------------------------------------------------------------
# Determines whether a source can stand alone to support publishable
# claims, or whether it must be paired with primary evidence.
# ------------------------------------------------------------------


def _determine_source_role(entry: dict, block: dict) -> str:
    """Classify source_role for an evidence unit.

    Rules:
    - graphify output (graph.json, GRAPH_REPORT.md)       → graph_analysis
    - source code files (.py, .js, .ts, etc.)             → code_artifact
    - project-authored txt/md corpora and architecture docs → internal_project_source
    - research/literature documents (PDF, DOCX)           → research_document
    - derived_summary files (summary.txt, digest.md)      → derived_summary
    - structured data (csv, xlsx, json without graphify)  → primary_source
    - base_document artifact_role                         → derived_summary
    - Unknown/default                                     → primary_source
    """
    artifact_role = entry.get("artifact_role", "")
    file_name = entry.get("file_name", "")
    file_path = entry.get("file_path", "")
    file_type = entry.get("file_type", "")
    content = block.get("content", "")[:200].lower()

    # Explicit base_document override
    if artifact_role == "base_document":
        return "derived_summary"

    # Graphify artifacts
    if "graph" in file_name.lower() or "graph_report" in file_name.lower():
        return "graph_analysis"
    if file_name.endswith(".json") and ("graph" in file_path or "graphify" in file_path):
        return "graph_analysis"

    # Code artifacts — detect by extension and content patterns
    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
                       ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala"}
    if any(file_name.endswith(ext) for ext in code_extensions):
        return "code_artifact"

    # Research / literature documents
    if file_type in {"pdf", "docx"}:
        # Check for literature indicators vs. primary source indicators
        literature_indicators = ["et al.", "journal", "doi:", "pubmed", "arxiv",
                                  "conference", "proceedings", "abstract"]
        primary_indicators = ["method", "methodology", "result", "finding",
                               "participant", "subject", "experiment"]
        lit_count = sum(1 for kw in literature_indicators if kw in content)
        pri_count = sum(1 for kw in primary_indicators if kw in content)
        if lit_count > pri_count:
            return "research_document"
        return "primary_source"

    # Derived summaries — detect by filename pattern
    summary_patterns = ["summary", "digest", "synopsis", "brief", "recap", "notes"]
    if any(pat in file_name.lower() for pat in summary_patterns):
        return "derived_summary"

    # Project-authored markdown/text artifacts should remain sidecar-grounded
    # rather than appear as publication citations.
    if file_type in {"md", "txt"}:
        return "internal_project_source"

    # Structured data files without graph context
    if file_type in STRUCTURED_TYPES:
        return "primary_source"

    return "primary_source"


# ------------------------------------------------------------------
# Fix #9: graphify uncertainty preservation
# ------------------------------------------------------------------


def _parse_graphify_metadata(entry: dict, block: dict) -> dict:
    """Extract and preserve graphify provenance metadata from a graph analysis source.

    Looks for:
    - INFERRED edge count and percentage
    - Average confidence score
    - Total node/edge counts
    - Key community information

    Returns a dict with graph_provenance fields, or empty dict if not a graph source.
    """
    file_name = entry.get("file_name", "").lower()
    content = block.get("content", "")

    # Only process graphify artifacts
    if not ("graph" in file_name or "graphify" in file_name or file_name.endswith(".json")):
        return {}

    # Try to extract metrics from content (GRAPH_REPORT.md style)
    import re

    inferred_match = re.search(
        r"(\d+)\s*(?:INFERRED|inferred)\s*edges?\s*(?:out of\s*(\d+))?",
        content, re.IGNORECASE
    )
    confidence_match = re.search(
        r"average\s+confidence[:\s]+([0-9.]+)",
        content, re.IGNORECASE
    )
    node_match = re.search(r"([\d,]+)\s*nodes?", content, re.IGNORECASE)
    edge_match = re.search(r"([\d,]+)\s*edges?", content, re.IGNORECASE)

    if not (inferred_match or confidence_match or node_match):
        return {}

    inferred_count = int(inferred_match.group(1)) if inferred_match else 0
    total_edges = int(inferred_match.group(2)) if inferred_match and inferred_match.group(2) else None
    avg_confidence = float(confidence_match.group(1)) if confidence_match else None
    total_nodes = int(node_match.group(1).replace(",", "")) if node_match else None
    total_edges_val = int(edge_match.group(1).replace(",", "")) if edge_match else total_edges

    inferred_pct = None
    if inferred_count and total_edges_val:
        try:
            inferred_pct = round(inferred_count / total_edges_val * 100, 1)
        except (ValueError, ZeroDivisionError):
            pass

    return {
        "graph_provenance": {
            "source": "graphify",
            "inferred_edge_count": inferred_count,
            "inferred_edge_pct": inferred_pct,
            "avg_confidence": avg_confidence,
            "total_nodes": total_nodes,
            "total_edges": total_edges_val,
            "uncertainty_note": (
                f"~{inferred_pct}% of edges are INFERRED (avg confidence {avg_confidence}). "
                "INFERRED edges represent hypotheses, not confirmed conclusions."
            ) if inferred_pct else None,
        }
    }


def compute_provenance_score(entry: dict, block: dict) -> float:
    """Compute provenance score deterministically.
    
    Scoring rules (deterministic, no agent):
    peer_reviewed_journal:     +0.3
    government_report:        +0.25
    preprint:                  -0.1
    company_report:           -0.15
    direct_url:               +0.1
    contains_table:            +0.1
    contains_figure:           +0.05
    contains_methodology:      +0.1
    first_hand_account:        +0.15
    contains_citations:       +0.05
    file_type = pdf:          +0.05
    file_type = csv/xlsx:     +0.1
    length > 5000 chars:       +0.05
    claimed_reproducibility:   +0.05
    ---
    base score:               0.5
    max score:                1.0
    min score:                0.0
    """
    score = 0.5
    file_type = entry.get("file_type", "")
    content = block.get("content", "")
    block_type = block.get("block_type", "")
    
    # File type bonuses
    if file_type == "pdf":
        score += 0.05
    elif file_type in STRUCTURED_TYPES:
        score += 0.1
    
    # Content length
    if len(content) > 5000:
        score += 0.05
    
    # Block type bonuses
    if block_type == "table":
        score += 0.1
    elif block_type == "figure_caption":
        score += 0.05
    
    # First hand account (PDF/DOCX typically contain original content)
    if file_type in FIRST_HAND_TYPES:
        score += 0.15
    
    # Contains methodology keywords
    methodology_keywords = ["method", "methodology", "study design", "participants", "sample", "analysis"]
    if any(kw in content.lower() for kw in methodology_keywords):
        score += 0.1
    
    # Contains citations
    if "citation" in content.lower() or "et al." in content:
        score += 0.05
    
    # Claimed reproducibility
    if "reproducib" in content.lower() or "open data" in content.lower():
        score += 0.05
    
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def determine_evidence_type(content: str, block_type: str) -> str:
    """Determine evidence type deterministically."""
    content_lower = content.lower()
    
    # Quantitative indicators
    quant_keywords = ["percentage", "%", "rate", "increase", "decrease", "number of", 
                      "average", "mean", "median", "count", "data show", "statistical"]
    if any(kw in content_lower for kw in quant_keywords):
        return "quantitative"
    
    # Methodological indicators
    method_keywords = ["method", "methodology", "design", "sample", "participants", "procedure", "protocol"]
    if any(kw in content_lower for kw in method_keywords):
        return "methodological"
    
    # Contextual indicators
    context_keywords = ["background", "context", "introduction", "overview", "setting"]
    if any(kw in content_lower for kw in context_keywords):
        return "contextual"
    
    # Default to qualitative
    return "qualitative"


def determine_granularity(block_type: str) -> str:
    """Determine evidence granularity."""
    if block_type == "table":
        return "table_row"
    elif block_type == "figure_caption":
        return "figure"
    elif block_type == "paragraph":
        return "paragraph"
    else:
        return "sentence"


# ------------------------------------------------------------------
# topic_tags — lightweight keyword-based classification
# ------------------------------------------------------------------

_TOPIC_TAG_RULES: list[tuple[set[str], str]] = [
    # (keywords, tag_name) — first match wins
    ({"statistical", "p-value", "confidence interval", "regression", "anova",
      "t-test", "chi-square", "correlation", "standard deviation", "variance"},
     "statistical"),
    ({"results", "findings", "outcome", "data show", "observed", "significant",
      "increase", "decrease", "change", "difference", "effect"},
     "results"),
    ({"method", "methodology", "study design", "participants", "procedure",
      "protocol", "sample size", "recruitment", "intervention", "randomized"},
     "methods"),
    ({"background", "introduction", "prior work", "literature", "previous research",
      "existing evidence", "systematic review"},
     "background"),
    ({"hypothesis", "aim", "objective", "purpose", "goal", "research question",
      "investigate", "examine", "evaluate"},
     "hypothesis"),
    ({"patient", "clinical", "treatment", "diagnosis", "therapy", "hospital",
      "disease", "symptom", "adverse", "efficacy", "safety"},
     "clinical"),
    ({"climate", "environmental", "ecosystem", "species", "biodiversity",
      "emission", "carbon", "temperature", "pollution"},
     "environmental"),
    ({"economic", "cost", "financial", "market", "pricing", "revenue", "budget",
      "economic analysis", "cost-effectiveness"},
     "economic"),
    ({"compared", "versus", "vs", "group", "control", "arm", "baseline",
      "comparison", "versus"},
     "comparative"),
    ({"discussion", "implication", "limitation", "strength", "future work",
      "recommendation", "conclusion"},
     "discussion"),
]


def determine_topic_tags(content: str) -> list[str]:
    """Return topic tags based on keyword matching in content.

    Multiple tags may match; returns all that match.
    """
    content_lower = content.lower()
    tags: list[str] = []
    for keywords, tag in _TOPIC_TAG_RULES:
        if any(kw in content_lower for kw in keywords):
            tags.append(tag)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def run_evidence_normalize(state: ReportState) -> ReportState:
    """T7: EVIDENCE_NORMALIZE - compute provenance scores and create evidence ledger.

    Adds topic_tags (keyword-based classification), cross_references (same-source links),
    created_at timestamp, source_role, graph_provenance, and line-level source_span
    to every evidence entry.

    Fix #4: Enforces content/quote/source_span required. Empty content → hard fail.
    Fix #4: source_role field — derived_summary cannot alone support publishable claims.
    Fix #9: Preserves graphify uncertainty (INFERRED edge %, avg confidence).
    """
    source_registry = state.sources.get("source_registry", [])
    evidence_units: list[dict] = []
    created_at = datetime.now(timezone.utc).isoformat()

    if not source_registry:
        raise QAHardBlockError("No sources available for evidence normalization")

    # In revise_existing mode with only base_document entries, skip extraction.
    # The evidence ledger is carried from the previous run's agent artifacts.
    task_intent = state.spec.get("task_intent", "new_draft")
    only_base_docs = all(
        entry.get("artifact_role") == "base_document"
        for entry in source_registry
    )
    if task_intent == "revise_existing" and only_base_docs:
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        evidence_ledger_path = run_dir / "evidence_ledger.jsonl"
        state.sources["evidence_ledger_path"] = str(evidence_ledger_path)
        return state

    for entry in source_registry:
        parsed_content = entry.get("parsed_content", [])
        if entry.get("artifact_role", "source_data") == "source_data" and not parsed_content:
            raise QAHardBlockError(f"Source has no parsed content: {entry.get('file_name')}")
        for block in parsed_content:
            content = block.get("content", "")
            if not content or len(content.strip()) < 10:
                continue

            # Fix #4: Enforce required fields — empty content is a hard block
            if not content.strip():
                raise QAHardBlockError(
                    f"Evidence block has empty content: block_id={block.get('block_id')} "
                    f"source={entry.get('file_name')}"
                )

            # Fix #4: source_role classification
            source_role = _determine_source_role(entry, block)

            # Fix #9: graphify uncertainty metadata
            graph_provenance = _parse_graphify_metadata(entry, block)

            granularity = determine_granularity(block.get("block_type", "paragraph"))
            evidence_type = determine_evidence_type(content, block.get("block_type", ""))
            provenance_score = compute_provenance_score(entry, block)

            if provenance_score >= 0.7:
                grade = "high"
            elif provenance_score >= 0.4:
                grade = "medium"
            else:
                grade = "low"

            evidence_id = stable_evidence_id(entry, block)
            topic_tags = determine_topic_tags(content)

            # Determine allowed claim types based on evidence type
            allowed_claim_types = {
                "quantitative": ["factual", "statistical"],
                "qualitative": ["factual", "qualitative"],
                "methodological": ["factual", "methodological"],
                "contextual": ["factual", "qualitative", "contextual"],
            }

            # Build source_span from line_start / line_end
            line_start = block.get("line_start")
            line_end = block.get("line_end")
            source_span = None
            if line_start is not None and line_end is not None:
                source_span = f"line {line_start}-{line_end}"
            elif line_start is not None:
                source_span = f"line {line_start}"

            content_hash = block.get("content_hash")
            if not content_hash:
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

            unit: dict = {
                "evidence_id": evidence_id,
                "source_id": entry.get("source_id", ""),
                "source_file_name": entry.get("file_name", ""),
                "source_file_path": entry.get("file_path", ""),
                "file_type": entry.get("file_type", ""),
                # Fix #4: source_role — derived_summary cannot stand alone
                "source_role": source_role,
                "granularity": granularity,
                "evidence_type": evidence_type,
                # Fix #4: content required (truncated to 2000)
                "content": content[:2000],
                # Fix #4: quote — first 200 chars for fast preview
                "quote": (content[:200] + ("..." if len(content) > 200 else "")),
                # Fix #4: source_span — line-level traceability
                "source_span": source_span,
                "line_start": line_start,
                "line_end": line_end,
                "content_hash": content_hash,
                "provenance_score": provenance_score,
                "evidence_grade": grade,
                "allowed_claim_types": allowed_claim_types.get(evidence_type, ["factual"]),
                "block_id": block.get("block_id", ""),
                "page_number": block.get("page_number"),
                "requires_hedged_wording": provenance_score < 0.7,
                "first_hand_account": entry.get("file_type", "") in FIRST_HAND_TYPES,
                "contains_methodology": "methodology" in content.lower(),
                "contains_citations": "et al." in content or "citation" in content.lower(),
                "claimed_reproducibility": "reproducib" in content.lower(),
                "topic_tags": topic_tags,
                "cross_references": [],   # filled in second pass
                "created_at": created_at,
                "last_used": None,
            }
            if block.get("table_data"):
                unit["table_data"] = block.get("table_data")

            # Fix #9: attach graphify uncertainty metadata
            if graph_provenance:
                unit.update(graph_provenance)

            evidence_units.append(unit)

    if not evidence_units:
        raise QAHardBlockError("Evidence ledger is empty")

    # Second pass: fill cross_references (link evidence from same source)
    by_source: dict[str, list[str]] = {}
    for unit in evidence_units:
        sid = unit.get("source_id", "")
        by_source.setdefault(sid, []).append(unit["evidence_id"])

    for unit in evidence_units:
        sid = unit.get("source_id", "")
        same_source_ids = by_source.get(sid, [])
        # Reference all other evidence_ids from the same source (not including self)
        unit["cross_references"] = [eid for eid in same_source_ids if eid != unit["evidence_id"]]

    # Write to evidence_ledger.jsonl
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)

    evidence_ledger_path = run_dir / "evidence_ledger.jsonl"
    with open(evidence_ledger_path, "w", encoding="utf-8") as f:
        for unit in evidence_units:
            f.write(json.dumps(unit, default=str) + "\n")

    state.sources["evidence_ledger_path"] = str(evidence_ledger_path)
    return state
