"""EVIDENCE_NORMALIZE node - deterministic evidence scoring."""
import hashlib
import json
import re
from datetime import datetime, timezone
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..artifact_contract import stable_evidence_id
from ..language import CJK_RE
from ..parsers.structured_parser import is_placeholder_value


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
    - source_data markdown/text notes                     → internal_project_source
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

    # Literature/bibliography sources in md/txt form are research documents:
    # the academic gates (scholarly quality, reference verification) key off
    # this role, and without it every literature note lands in
    # internal_project_source and the paper path reports "no research
    # documents" forever. Detect by filename token or by citation shape
    # ("Author, X. (2014)." patterns) in the block.
    literature_name = any(
        token in file_name.lower()
        for token in ("literature", "reference", "bibliograph", "文獻", "书目", "書目")
    )
    if file_type in {"md", "txt"} and (
        literature_name or re.search(r"\(\d{4}\)\.", content)
    ):
        return "research_document"

    # A user/agent-curated Markdown or text source supplied as source_data is
    # an accepted project source, even when the filename contains "notes".
    # Otherwise Chinese lab workflows that transcribe scanned PDFs into
    # source_notes.md are hard-blocked as derived-only evidence.
    if artifact_role == "source_data" and file_type in {"md", "txt"}:
        return "internal_project_source"

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

    # Research / literature documents.
    #
    # The md/txt branch above already carries the Chinese filename tokens; this
    # branch had English keywords only, so for a Chinese PDF or Word document
    # both counts were zero, the strict comparison failed, and every one of
    # them came back primary_source. A Chinese journal paper could not be
    # recognised as literature at all, and the evidence-policy warning kept
    # telling those users to add literature references they had already
    # attached. Literature is far more likely to arrive as a PDF than as
    # markdown, so this is the branch that most needed the tokens.
    if file_type in {"pdf", "docx"}:
        literature_indicators = ["et al.", "journal", "doi:", "pubmed", "arxiv",
                                  "conference", "proceedings", "abstract",
                                  "期刊", "學報", "学报", "論文", "论文", "文獻",
                                  "文献", "研討會", "研讨会", "卷", "頁碼", "页码"]
        primary_indicators = ["method", "methodology", "result", "finding",
                               "participant", "subject", "experiment",
                               "方法", "步驟", "步骤", "結果", "结果", "受試",
                               "受试", "實驗", "实验", "量測", "测量"]
        lit_count = sum(1 for kw in literature_indicators if kw in content)
        pri_count = sum(1 for kw in primary_indicators if kw in content)
        if literature_name or lit_count > pri_count:
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


_MD_TABLE_SEPARATOR_RE = re.compile(r"\|\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|")


def _is_markdown_table(content: str) -> bool:
    """True when a parsed paragraph block is really a Markdown pipe table.

    Markdown and DOCX sources are ingested paragraph by paragraph, so a table
    inside one arrives typed as prose. It then missed both the table bonus and
    the structured-row bonus, and the same grading-weight table scored high as
    a CSV row but medium inside a handbook — leaving FD to forbid measured
    wording on numbers the source states exactly.
    """
    if content.count("|") < 4:
        return False
    return bool(_MD_TABLE_SEPARATOR_RE.search(content))


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
    markdown_table = _is_markdown_table(content)
    if block_type == "table" or markdown_table:
        score += 0.1
    elif block_type == "figure_caption":
        score += 0.05

    # First hand account (PDF/DOCX typically contain original content)
    if file_type in FIRST_HAND_TYPES:
        score += 0.15

    # First-hand quantitative measurements: a structured data row carrying
    # several numeric values is the user's own measured data — the same
    # language-neutral signal determine_evidence_type uses for
    # "quantitative". Without this bonus a CSV of the user's measurements
    # can never reach evidence_grade=high, and FD then forbids measured
    # wording on the very numbers the report exists to state.
    if (
        block_type in {"csv_row", "table_row", "data_row"} or markdown_table
    ) and len(_NUMERIC_TOKEN_RE.findall(content)) >= 2:
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


_NUMERIC_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?")

_MEASURED_COL_RE = re.compile(r"measured|實測", re.IGNORECASE)
# A reference curve is rarely labelled "theoretical" on a real sheet. It is the
# manufacturer's rated or nominal figure, and both runs that motivated this
# carried exactly that — "Rated Effectiveness" and 廠商標稱有效度 — so the
# comparison against it never fired in either language, despite the code
# carrying an output template for both. Word boundaries on the English tokens
# keep "Flow Rate" from reading as a rated value.
_THEORETICAL_COL_RE = re.compile(
    r"theoretical|theory|\brated\b|\bnominal\b|\bexpected\b|\bpredicted\b"
    r"|理論|理论|標稱|标称|額定|额定",
    re.IGNORECASE,
)
_ERROR_COL_RE = re.compile(r"error|誤差", re.IGNORECASE)
_AMOUNT_COL_RE = re.compile(
    r"total|subtotal|amount|cost|price|spend|budget"
    r"|小計|合計|總計|金額|費用|價格|預算|成本",
    re.IGNORECASE,
)


#: Column headers that mark rows as mutually exclusive alternatives rather
#: than line items. Totalling a comparison of options produces a number with
#: no referent — you buy one of them, not all three — and registering that as
#: high-grade citable evidence is exactly the confident-but-meaningless figure
#: the gates exist to keep out of a document.
_OPTION_TABLE_COL_RE = re.compile(
    r"方案|選項|備選|option|alternative|scenario", re.IGNORECASE
)


def _format_amount(value: float) -> str:
    """Thousands-separated, and only as precise as the data actually is."""
    if abs(value - round(value)) < 1e-9:
        return f"{round(value):,}"
    return f"{value:,.2f}"


def _is_product_column(numeric: dict[str, list[float]], candidate: str) -> bool:
    """True when a column equals the elementwise product of two others.

    A quote sheet's line-total column (單價 × 數量 = 小計) is the one worth
    summing even when its header carries no recognizable amount word.
    """
    values = numeric[candidate]
    others = [c for c in numeric if c != candidate]
    for i, left in enumerate(others):
        for right in others[i + 1:]:
            if all(
                abs(numeric[left][k] * numeric[right][k] - values[k]) <= 1e-6
                for k in range(len(values))
            ):
                return True
    return False


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least-squares slope and R² of y against x."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    syy = sum((y - mean_y) ** 2 for y in ys)
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 1.0
    return slope, r2


def _derived_stats_units(source_registry: list, created_at: str) -> list[dict]:
    """Compute citable derived statistics from structured measurement rows.

    The quantitative analysis a reader actually grades — slope versus the
    theoretical slope, fit quality, error range — cannot come from the
    authoring agent: a number with no evidence behind it is exactly what
    the factuality gates block. Deriving the standard statistics here and
    recording them as regular ledger entries (method noted in a
    ``derivation`` field) makes that analysis citable.
    """
    units: list[dict] = []
    for entry in source_registry:
        if entry.get("file_type") not in STRUCTURED_TYPES:
            continue
        rows: list[dict] = []
        for block in entry.get("parsed_content", []) or []:
            if block.get("block_type") not in {"csv_row", "table_row", "data_row"}:
                continue
            try:
                row = json.loads(block.get("content", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(row, dict):
                rows.append(row)
        # A fit or an error range needs three points; a column total is
        # meaningful from two rows on, and a two-line budget still needs one.
        if len(rows) < 2:
            continue
        columns = list(rows[0].keys())
        numeric: dict[str, list[float]] = {}
        for col in columns:
            try:
                numeric[col] = [
                    float(str(r.get(col, "")).replace(",", "")) for r in rows
                ]
            except (TypeError, ValueError):
                continue
        if not numeric:
            continue

        measured_col = next(
            (c for c in columns if c in numeric and _MEASURED_COL_RE.search(c)), None
        )
        theoretical_col = next(
            (c for c in columns if c in numeric and _THEORETICAL_COL_RE.search(c)), None
        )
        error_col = next(
            (c for c in columns if c in numeric and _ERROR_COL_RE.search(c)), None
        )
        x_col = next(
            (
                c
                for c in columns
                if c in numeric
                and c not in (measured_col, theoretical_col, error_col)
            ),
            None,
        )
        zh = bool(CJK_RE.search("".join(columns)))
        file_name = entry.get("file_name", "")

        contents: list[tuple[str, dict]] = []
        if measured_col and x_col and len(rows) >= 3:
            slope, r2 = _linear_fit(numeric[x_col], numeric[measured_col])
            if zh:
                text = (
                    f"衍生統計(來源:{file_name}):以最小平方法擬合 {measured_col} 對 "
                    f"{x_col},斜率為 {slope:.3g},決定係數 R² 為 {r2:.4f}。"
                )
            else:
                text = (
                    f"Derived statistics from {file_name}: least-squares slope of "
                    f"{measured_col} versus {x_col} is {slope:.3g} with R² = {r2:.4f}."
                )
            if theoretical_col:
                t_slope, _ = _linear_fit(numeric[x_col], numeric[theoretical_col])
                if zh:
                    text += f"{theoretical_col} 對 {x_col} 的理論斜率為 {t_slope:.3g}。"
                else:
                    text += (
                        f" The slope of {theoretical_col} versus {x_col} is "
                        f"{t_slope:.3g}."
                    )
            contents.append(
                (
                    text,
                    {
                        "method": "least_squares_fit",
                        "input_columns": [c for c in (x_col, measured_col, theoretical_col) if c],
                    },
                )
            )
        if error_col and len(rows) >= 3:
            values = numeric[error_col]
            e_min, e_max = min(values), max(values)
            e_mean = sum(values) / len(values)
            if zh:
                text = (
                    f"衍生統計(來源:{file_name}):{error_col} 介於 {e_min:.3g} 至 "
                    f"{e_max:.3g},平均為 {e_mean:.3g}。"
                )
            else:
                text = (
                    f"Derived statistics from {file_name}: {error_col} ranges from "
                    f"{e_min:.3g} to {e_max:.3g} with a mean of {e_mean:.3g}."
                )
            contents.append(
                (text, {"method": "summary_stats", "input_columns": [error_col]})
            )

        # A budget, quote sheet, or cost table is read for its total, and the
        # total is the one number on the page that no row states. Without it
        # the author either omits the figure the reader came for or writes an
        # arithmetic result the factuality gates correctly refuse to publish.
        compares_alternatives = any(_OPTION_TABLE_COL_RE.search(c) for c in columns)
        amount_cols = [
            c
            for c in columns
            if c in numeric
            and c not in (measured_col, theoretical_col, error_col)
            and _AMOUNT_COL_RE.search(c)
            and not compares_alternatives
        ]
        total_col = next(
            (c for c in amount_cols if _is_product_column(numeric, c)),
            amount_cols[-1] if amount_cols else None,
        )
        if total_col is None and len(numeric) >= 3 and not compares_alternatives:
            total_col = next(
                (
                    c
                    for c in columns
                    if c in numeric
                    and c not in (measured_col, theoretical_col, error_col)
                    and _is_product_column(numeric, c)
                ),
                None,
            )
        if total_col:
            values = numeric[total_col]
            total = sum(values)
            largest = max(values)
            if zh:
                text = (
                    f"衍生統計(來源:{file_name}):{total_col} 欄合計為 "
                    f"{_format_amount(total)},共 {len(values)} 筆,"
                    f"單筆最高為 {_format_amount(largest)}。"
                )
            else:
                text = (
                    f"Derived statistics from {file_name}: the {total_col} column "
                    f"totals {_format_amount(total)} across {len(values)} rows, "
                    f"with a largest single value of {_format_amount(largest)}."
                )
            contents.append(
                (text, {"method": "column_total", "input_columns": [total_col]})
            )

        for index, (content, derivation) in enumerate(contents):
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            units.append({
                "evidence_id": f"E_{entry.get('source_id', '')}_{digest[:10]}",
                "source_id": entry.get("source_id", ""),
                "source_file_name": file_name,
                "source_file_path": entry.get("file_path", ""),
                "file_type": entry.get("file_type", ""),
                "source_role": "source_data",
                "granularity": "paragraph",
                "evidence_type": "quantitative",
                "content": content,
                "quote": content[:200],
                "source_span": None,
                "line_start": None,
                "line_end": None,
                "content_hash": digest[:16],
                "provenance_score": 0.75,
                "evidence_grade": "high",
                "allowed_claim_types": ["factual", "statistical"],
                "block_id": f"derived_{index}",
                "page_number": None,
                "requires_hedged_wording": False,
                "first_hand_account": False,
                "contains_methodology": False,
                "contains_citations": False,
                "claimed_reproducibility": False,
                "topic_tags": determine_topic_tags(content),
                "cross_references": [],
                "created_at": created_at,
                "last_used": None,
                "derivation": derivation,
            })
    return units


_ROW_BLOCK_TYPES = {"csv_row", "table_row", "data_row"}


def _row_values_lower(content: str, block_type: str) -> str | None:
    """Lowercased cell values of a structured row, placeholders dropped.

    None when the block is not a serialized row, so callers keep their
    existing whole-content behaviour for prose and whole-table blocks.
    """
    if block_type not in _ROW_BLOCK_TYPES:
        return None
    try:
        record = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(record, dict):
        return None
    return " ".join(
        str(value) for value in record.values()
        if not is_placeholder_value(value)
    ).lower()


def determine_evidence_type(content: str, block_type: str) -> str:
    """Determine evidence type deterministically.

    Keyword matching alone is English-only and misses tabular data entirely:
    a CSV row serialized as JSON carries measurements but no prose keywords,
    and Chinese sources carry no English keywords at all. Both used to fall
    through to "qualitative", which then blocked statistical claims (FB needs
    quantitative evidence) and capped wording strength for the user's own
    measurement data. Numeric density and structured-row shape are
    language-neutral quantitative signals, checked first.
    """
    content_lower = content.lower()

    # For a structured row, the keys are column names — labels, not readings.
    # Judging "is this a measurement" on the whole serialized record let a
    # header do the deciding: a row of dashes under "Efficiency (%)" came out
    # quantitative on the strength of the "%" in the column name. Weigh the
    # values instead, ignoring cells nobody filled in. Only the quantitative
    # decision narrows this way; a column named "Method" really does say
    # something about the row, so the ladder below still reads the full record.
    measured_lower = _row_values_lower(content, block_type)
    if measured_lower is not None and not measured_lower.strip():
        # Every cell was a placeholder; there is no measurement here.
        return "qualitative"
    quant_scope = content_lower if measured_lower is None else measured_lower

    # Structured data rows (CSV/table ingestion) carrying several numeric
    # values are measurements, whatever language surrounds them.
    numeric_tokens = _NUMERIC_TOKEN_RE.findall(quant_scope)
    # "table" is the whole-table block the PDF, DOCX, and markdown parsers all
    # emit; the others are single-row shapes from CSV ingestion. Listing only
    # the row shapes meant a measurement table from any source but a CSV fell
    # through to keyword matching and came out qualitative.
    if block_type in {"csv_row", "table_row", "data_row", "table"} and len(numeric_tokens) >= 2:
        return "quantitative"
    # Shape comes from the whole record; the numbers come from the values.
    if len(numeric_tokens) >= 3 and content_lower.count(":") >= 3 and content_lower.count('"') >= 4:
        # JSON-ish record with several numeric fields.
        return "quantitative"

    # Quantitative indicators (English + Chinese)
    quant_keywords = ["percentage", "%", "rate", "increase", "decrease", "number of",
                      "average", "mean", "median", "count", "data show", "statistical",
                      "百分比", "比率", "平均", "中位", "次數", "統計", "增加", "減少", "量測值"]
    if any(kw in quant_scope for kw in quant_keywords):
        return "quantitative"

    # Methodological indicators (English + Chinese)
    method_keywords = ["method", "methodology", "design", "sample", "participants", "procedure", "protocol",
                       "方法", "步驟", "程序", "樣本", "受試", "實驗設計"]
    if any(kw in content_lower for kw in method_keywords):
        return "methodological"

    # Contextual indicators (English + Chinese)
    context_keywords = ["background", "context", "introduction", "overview", "setting",
                        "背景", "緒論", "概述", "前言"]
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

    # In revise_existing mode with only base_document entries, reuse a ledger
    # carried from a previous run's agent artifacts when one exists. When it
    # does not (a fresh revision run), fall through and ingest the base
    # document itself: its content is the ground truth a faithful revision
    # cites. Previously this early-returned unconditionally, recording a
    # ledger path that no file ever backed — claims then had no possible
    # evidence and validation failed far downstream with an empty-ledger
    # error nobody could trace back to prepare.
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
        if evidence_ledger_path.exists():
            return state
        # Base-document entries carry no parsed_content (ingestion only
        # parses source_data); synthesize paragraph blocks from the sections
        # BASE_DOCUMENT_PARSE just extracted so the normal ingestion loop
        # below can build the ledger.
        sections_path = run_dir / "base_document_sections.json"
        if sections_path.exists():
            with open(sections_path, encoding="utf-8") as f:
                base_sections = json.load(f)
            blocks = []
            for sid, section_content in base_sections.items():
                for index, para in enumerate(re.split(r"\n\s*\n", section_content or "")):
                    if para.strip():
                        blocks.append({
                            "content": para.strip(),
                            "block_type": "paragraph",
                            "block_id": f"base_{sid}_{index}",
                        })
            for entry in source_registry:
                if entry.get("artifact_role") == "base_document" and not entry.get("parsed_content"):
                    entry["parsed_content"] = blocks
                    break

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

    # Citable derived statistics (slope, R², error summary) from structured
    # measurement rows — the analysis a reader grades, made evidence.
    evidence_units.extend(_derived_stats_units(source_registry, created_at))

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
