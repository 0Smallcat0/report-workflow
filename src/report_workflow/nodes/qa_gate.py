"""QA_GATE node - pass/fail decision based on factuality and citation reports."""
import json
import logging
import re
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..policies import get_policy
from ..runtime_support import PLACEHOLDER_TEXT, load_jsonl

# Internal alias for backward compatibility with local _load_jsonl references
_load_jsonl = load_jsonl
from .remediation_router import write_remediation_plan

logger = logging.getLogger(__name__)


def _banned_phrase_reasons(state: ReportState) -> list[str]:
    """Return hard-fail reasons if any banned phrase appears in merged draft."""
    reasons = []
    merged_path = state.drafts.get("merged_draft_md")
    if not merged_path or not Path(merged_path).exists():
        return reasons

    merged_text = Path(merged_path).read_text(encoding="utf-8").lower()
    family = state.spec.get("report_family", "academic_report")
    policy = get_policy(family)
    banned = policy.banned_phrases

    found = []
    for phrase in banned:
        if phrase.lower() in merged_text:
            found.append(phrase)

    if found:
        reasons.append("banned phrases found in merged draft: " + ", ".join(found))
    return reasons


# ------------------------------------------------------------------
# Fix #8: Results section — empirical vs architectural_characterization
# ------------------------------------------------------------------


def _results_section_reasons(state: ReportState) -> list[str]:
    """Verify results section correctness.

    For academic_report (empirical_strict=True):
      - Claims of "improves / reduces / superior / better / faster"
        without empirical performance data → hard fail.
    """
    import re

    reasons = []
    family = state.spec.get("report_family", "academic_report")
    policy = get_policy(family)
    if not policy.results.empirical_strict:
        return reasons

    # Load results_mode — outline takes priority over blueprint
    # Fix #5: outline.sections.results.results_mode first, then blueprint fallback
    outline = state.plan.get("outline") or {}
    blueprint = state.plan.get("blueprint") or {}

    results_mode = "empirical"  # default
    outline_results = outline.get("sections", {}).get("results", {})
    if outline_results and "results_mode" in outline_results:
        results_mode = outline_results.get("results_mode", "empirical")
    else:
        blueprint_results = blueprint.get("sections", {}).get("results", {})
        results_mode = blueprint_results.get("results_mode", "empirical")

    if results_mode == "architectural_characterization":
        # Verify the outline/results section is labeled as such
        # (already set in blueprint; we just document the constraint)
        pass

    merged_path = state.drafts.get("merged_draft_md", "")
    if not merged_path or not Path(merged_path).exists():
        return reasons  # Let other checks catch missing draft

    merged_text = Path(merged_path).read_text(encoding="utf-8")

    # Find the Results section content
    # Split by headings — find # Results or ## Results
    section_pattern = re.compile(
        r"^#{1,2}\s+Results\s*$",
        re.MULTILINE | re.IGNORECASE
    )
    match = section_pattern.search(merged_text)
    if not match:
        return reasons  # No results section found

    results_start = match.end()
    # Find next heading (## something else) to delimit section
    next_heading = re.search(
        r"^#{1,2}\s+[^\n]+$",
        merged_text[results_start:],
        re.MULTILINE
    )
    if next_heading:
        results_content = merged_text[results_start:results_start + next_heading.start()]
    else:
        results_content = merged_text[results_start:]

    # Performance claim patterns — phrases that imply empirical results
    performance_claim_re = re.compile(
        r"\b(improves?|reduces?|better|worse|faster|slower|"
        r"superior|inferior|increase|decrease|"
        r"speedup|latency|throughput|accuracy|precision|recall|"
        r"gain|boost|enhanc|optimiz|speed)\b",
        re.IGNORECASE
    )
    performance_claims = performance_claim_re.findall(results_content)

    # Numeric result patterns — actual measured data
    numeric_result_re = re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:%|ms|μs|ns|s|Hz|MHz|GHz|"
        r"acc|precis|recall|f1|score|ratio|times|fold)\b",
        re.IGNORECASE
    )
    numeric_results = numeric_result_re.findall(results_content)

    if performance_claims and not numeric_results:
        if results_mode != "architectural_characterization":
            reasons.append(
                "results section contains performance claims "
                f"(e.g. {performance_claims[0]!r}) but no numeric measurements found. "
                "Set results_mode=architectural_characterization in outline, "
                "or provide actual performance data."
            )

    return reasons


def _source_diversity_reasons(state: ReportState) -> list[str]:
    """For academic_report: require graph + code + research evidence diversity.

    academic_report hard-fail if:
    1. No graph_analysis evidence (graphify output)
    2. No code_artifact evidence (source code)
    3. No research_document evidence (literature)

    Also: any claim backed ONLY by derived_summary evidence → hard fail
    (derived_summary cannot stand alone for publishable claims).
    """
    reasons = []
    family = state.spec.get("report_family", "academic_report")
    policy = get_policy(family)
    if not policy.claim.primary_source_required:
        return reasons

    evidence_ledger = _load_jsonl(state.sources.get("evidence_ledger_path", ""))
    if not evidence_ledger:
        return reasons  # Empty ledger handled by other checks; skip diversity check here

    # Fix #2: academic_report requires at least 10 evidence entries
    if len(evidence_ledger) < 10:
        reasons.append(
            f"academic_report requires at least 10 evidence entries "
            f"but found {len(evidence_ledger)}"
        )

    # Collect source_role distribution
    source_roles: set[str] = set()
    derived_only_claims: list[str] = []

    claim_matrix = state.plan.get("claim_matrix", {})
    claims = claim_matrix.get("claims", [])

    # Build evidence_id → source_role lookup
    evidence_roles: dict[str, str] = {}
    for ev in evidence_ledger:
        eid = ev.get("evidence_id", "")
        role = ev.get("source_role", "primary_source")
        evidence_roles[eid] = role
        source_roles.add(role)

    # Check each claim's evidence composition
    for claim in claims:
        claim_id = claim.get("claim_id", "<missing>")
        evidence_ids = claim.get("evidence_ids", [])
        if not evidence_ids:
            continue

        roles_for_claim = set(
            evidence_roles.get(eid, "primary_source") for eid in evidence_ids
        )

        # Fix #4: derived_summary cannot stand alone for publishable claims
        if roles_for_claim == {"derived_summary"}:
            derived_only_claims.append(claim_id)

        # For academic_report: if all evidence is derived_summary, that's a hard fail
        # (we allow mixed derived_summary + primary, but not ONLY derived_summary)

    # Check 1: graph_analysis required
    if "graph_analysis" not in source_roles:
        reasons.append(
            "academic_report requires graph_analysis evidence "
            "(e.g. graphify output) — none found in evidence ledger"
        )

    # Check 2: code_artifact required
    if "code_artifact" not in source_roles:
        reasons.append(
            "academic_report requires code_artifact evidence "
            "(source code files) — none found in evidence ledger"
        )

    # Check 3: research_document required
    if "research_document" not in source_roles:
        reasons.append(
            "academic_report requires research_document evidence "
            "(literature/research PDFs or DOCXs) — none found in evidence ledger"
        )

    # Fix #4: derived_summary alone check
    if derived_only_claims:
        reasons.append(
            "claims backed ONLY by derived_summary evidence (no primary evidence): " +
            ", ".join(derived_only_claims[:5])
        )

    # Check 4: single evidence ID supporting all claims
    all_claim_evidence_ids: list[str] = []
    for claim in claims:
        all_claim_evidence_ids.extend(claim.get("evidence_ids", []))

    from collections import Counter
    if all_claim_evidence_ids:
        evidence_counts = Counter(all_claim_evidence_ids)
        most_common_id, most_common_count = evidence_counts.most_common(1)[0]
        if most_common_count == len(claims) and len(claims) > 1:
            reasons.append(
                f"single evidence ID {most_common_id!r} supports ALL claims — "
                "evidence diversity required for academic_report"
            )

    return reasons


def _artifact_hard_fail_reasons(state: ReportState) -> list[str]:
    reasons = []

    source_registry = state.sources.get("source_registry", [])
    if not source_registry:
        reasons.append("source_registry is empty")
    elif not any(entry.get("parse_status") == "parsed" and entry.get("parsed_content") for entry in source_registry):
        reasons.append("no parsed source content")

    if not _load_jsonl(state.sources.get("evidence_ledger_path", "")):
        reasons.append("evidence ledger is empty")

    claims = state.plan.get("claim_matrix", {}).get("claims", [])
    if not claims:
        reasons.append("claim matrix is empty")

    outline_sections = state.plan.get("outline", {}).get("sections", {})
    if not outline_sections:
        reasons.append("outline is empty")

    section_drafts = state.drafts.get("section_drafts", {})
    if not section_drafts:
        reasons.append("section drafts are empty")
    for section_id, section_path in section_drafts.items():
        if not section_path or not Path(section_path).exists():
            reasons.append(f"section draft missing: {section_id}")
            continue
        text = Path(section_path).read_text(encoding="utf-8")
        if not text.strip():
            reasons.append(f"section draft empty: {section_id}")
        if PLACEHOLDER_TEXT in text:
            reasons.append(f"section draft is placeholder: {section_id}")

    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path", ""))
    if not sentence_map:
        reasons.append("sentence map is empty")

    merged_path = state.drafts.get("merged_draft_md")
    if not merged_path or not Path(merged_path).exists():
        reasons.append("merged draft is missing")
    else:
        merged_text = Path(merged_path).read_text(encoding="utf-8")
        if not merged_text.strip():
            reasons.append("merged draft is empty")
        if PLACEHOLDER_TEXT in merged_text:
            reasons.append("merged draft contains placeholder content")

    return reasons


def _citation_linkage_reasons(state: ReportState) -> list[str]:
    reasons = []
    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path", ""))
    if not sentence_map:
        return reasons

    merged_path = state.drafts.get("merged_draft_md")
    if not merged_path or not Path(merged_path).exists():
        return reasons

    placeholders = set(re.findall(r"\[CITE:([^\]]+)\]", Path(merged_path).read_text(encoding="utf-8")))
    missing = set()
    for sent in sentence_map:
        evidence_ids = [eid for eid in sent.get("evidence_ids", []) if eid]
        if not evidence_ids:
            continue
        expected = sent.get("citation_ids") or evidence_ids
        for cite_id in expected:
            if cite_id not in placeholders:
                missing.add(str(cite_id))

    if missing:
        reasons.append("missing citation placeholders for evidence-backed sentences: " + ", ".join(sorted(missing)))
    return reasons


def _write_qa_summary(state: ReportState) -> None:
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "qa_summary.json"
    payload = {
        "job_id": state.job_id,
        "qa_decision": state.qa.get("qa_decision"),
        "artifact_completeness_status": state.qa.get("artifact_completeness_status"),
        "hard_fail_reasons": state.qa.get("hard_fail_reasons", []),
        "citation_audit": state.citations.get("citation_audit", []),
        "factuality_report_path": state.qa.get("factuality_report_path"),
        "consistency_report_path": state.qa.get("consistency_report_path", ""),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    state.qa["qa_summary_path"] = str(path)


def run_qa_gate(state: ReportState) -> ReportState:
    """T14: QA_GATE - make pass/fail decision based on reports."""
    factuality_path = state.qa.get("factuality_report_path")

    qa_decision = "pass"
    hard_fail_reasons = _artifact_hard_fail_reasons(state)
    hard_fail_reasons.extend(_citation_linkage_reasons(state))
    hard_fail_reasons.extend(_banned_phrase_reasons(state))
    hard_fail_reasons.extend(_source_diversity_reasons(state))
    hard_fail_reasons.extend(_results_section_reasons(state))

    # Load factuality report
    if factuality_path and Path(factuality_path).exists():
        try:
            with open(factuality_path, encoding="utf-8") as f:
                factuality_report = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.exception(f"[QA_GATE] failed to load factuality report: {exc}")
            factuality_report = {}

        blocked_count = factuality_report.get("blocked_count", 0)
        disputed_count = factuality_report.get("disputed_count", 0)

        if blocked_count > 0:
            qa_decision = "hard_fail"
            # Extract blocked claim IDs for actionable error message
            blocked_claims = [
                c.get("claim_id", "?")
                for c in factuality_report.get("claims", [])
                if c.get("status") == "blocked"
            ]
            blocked_ids_str = ", ".join(blocked_claims)
            hint = (
                f"factuality blocked claims: {blocked_count} — "
                f"({blocked_ids_str}). "
                f"Edit claim_matrix.json and evidence_ledger.jsonl directly — "
                f"checkpoint files are NOT read by factuality_check. "
                f"Delete factuality_report.json before re-running validate."
            )
            hard_fail_reasons.append(hint)
        elif disputed_count > 0:
            qa_decision = "hard_fail"  # disputed = unverified inference, cannot waive
            hard_fail_reasons.append(f"factuality disputed claims: {disputed_count}")
    else:
        hard_fail_reasons.append("factuality report is missing")

    # Check citation audit
    citation_audit = state.citations.get("citation_audit", [])
    unresolved = [c for c in citation_audit if not c.get("resolved", False)]

    if unresolved:
        qa_decision = "hard_fail"
        hard_fail_reasons.append(f"unresolved citations: {len(unresolved)}")

    if hard_fail_reasons:
        qa_decision = "hard_fail"

    state.qa["qa_decision"] = qa_decision
    state.qa["artifact_completeness_status"] = "hard_fail" if hard_fail_reasons else "pass"
    state.qa["hard_fail_reasons"] = hard_fail_reasons
    _write_qa_summary(state)
    
    # If hard fail, update status
    if qa_decision == "hard_fail":
        state.update_status("failed")
        write_remediation_plan(state, hard_fail_reasons)
        raise QAHardBlockError("; ".join(hard_fail_reasons))
    
    return state
