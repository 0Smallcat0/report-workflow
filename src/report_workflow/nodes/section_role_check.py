"""SECTION_ROLE_CHECK node - verify IMRaD section role separation.

Runs before QA_GATE in the validate phase.

Validates that IMRaD sections maintain proper role boundaries:
  - Results: only presents findings (no interpretation)
  - Discussion: interprets results (no raw result restatement)
  - Methods: describes procedure (no conclusions)
  - Abstract: claims backed by evidence
  - Introduction: no results

Output: section_role_report.json
"""
import json
import re
from pathlib import Path

from ..state import ReportState
from ..runtime_support import write_json_artifact
from ..policies import get_policy


# Patterns that indicate wrong section content
RESULTS_INTRUSION_PATTERNS = [
    (r'\b(we conclude|we demonstrate|we show|this proves|this confirms)\b', 'conclusion'),
    (r'\b(the|these) results (suggest|indicate|show|prove|demonstrate)\b', 'interpretation'),
    (r'\bour (finding|result|evidence)\b', 'interpretation'),
]

DISCUSSION_INTRUSION_PATTERNS = [
    (r'\bmeasured\s+\d+', 'raw_result'),
    (r'\b(observed|found|recorded)\s+\d+', 'raw_result'),
    (r'\bpercentage\b', 'raw_result'),
    (r'\baverage\b', 'raw_result'),
]

METHODS_INTRUSION_PATTERNS = [
    (r'\b(we conclude|we suggest|we propose)\b', 'conclusion'),
    (r'\b(significant|significantly)\b', 'interpretation'),
    (r'\bshows (that|how)\b', 'interpretation'),
]

INTRODUCTION_INTRUSION_PATTERNS = [
    (r'\b(measured|observed|found)\s+\d+', 'result'),
    (r'\bpercentage\b', 'result'),
    (r'\bour (results|findings)\b', 'result'),
]


# Paper-roadmap sentence (only required for non-admissions academic_paper).
# Admissions mode intentionally strips the roadmap to keep the project-
# monograph tone.
_PAPER_ROADMAP_PATTERNS = [
    r"remainder of this (?:report|paper) is organized",
    r"the (?:report|paper) is structured as follows",
    r"this (?:report|paper) proceeds as follows",
    r"section\s+\d+\s+(?:presents|describes|introduces|discusses)",
]


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


def _split_by_sections(merged_text: str) -> dict[str, str]:
    """Split merged markdown into section_id -> content mapping."""
    sections = {}
    lines_by_section = []
    current_section = "preamble"
    current_lines = []

    for line in merged_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            if current_lines:
                lines_by_section.append((current_section, current_lines))
                current_lines = []
            heading = stripped[2:].strip().lower().replace(" ", "_")
            current_section = heading[:48]
        current_lines.append(line)

    if current_lines:
        lines_by_section.append((current_section, current_lines))

    for sid, lines in lines_by_section:
        sections[sid] = "\n".join(lines).strip()

    return sections


def _check_section(section_name: str, content: str, patterns: list) -> list[dict]:
    """Check content against intrusion patterns."""
    issues = []
    for pattern, intrusion_type in patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            context = content[max(0, match.start() - 50):match.end() + 50]
            issues.append({
                "section": section_name,
                "intrusion_type": intrusion_type,
                "pattern": pattern,
                "matched_text": match.group(0),
                "context": context,
                "severity": "hard" if intrusion_type in ("conclusion", "raw_result") else "soft",
            })
    return issues


def _check_thesis_spine(state: ReportState, intro_content: str) -> list[dict]:
    """Flag Introductions that drift away from the thesis spine.

    For admissions_report + new_draft, use explicit project_identity terms when
    present. revise_existing preserves the base document, so this guard is
    skipped. No project-specific default terms are applied here.
    """
    issues: list[dict] = []
    profile = state.spec.get("report_profile", "")
    intent = state.spec.get("task_intent", "new_draft")

    if profile != "admissions_report":
        return issues
    if intent != "new_draft":
        return issues

    identity = state.plan.get("project_identity") or state.spec.get("project_identity") or {}
    if not isinstance(identity, dict):
        return issues
    terms: list[str] = []
    for key in ("required_terms", "required_context_terms", "canonical_title_terms"):
        terms.extend(str(term).strip() for term in identity.get(key, []) or [] if str(term).strip())
    if not terms:
        return issues

    def term_present(term: str) -> bool:
        if re.fullmatch(r"[A-Za-z0-9_]+", term):
            return bool(re.search(rf"\b{re.escape(term)}\b", intro_content, re.IGNORECASE))
        parts = [part for part in re.split(r"[\s-]+", term) if part]
        if len(parts) > 1 and all(re.fullmatch(r"[A-Za-z0-9_]+", part) for part in parts):
            pattern = r"\b" + r"[\s-]+".join(re.escape(part) for part in parts) + r"\b"
            return bool(re.search(pattern, intro_content, re.IGNORECASE))
        return bool(re.search(re.escape(term), intro_content, re.IGNORECASE))

    hit_tokens = [term for term in terms if term_present(term)]
    if len(hit_tokens) < 2:
        issues.append({
            "section": "introduction",
            "intrusion_type": "thesis_spine_missing",
            "detail": (
                f"Introduction mentions only {len(hit_tokens)} thesis-spine concept(s); "
                "admissions-facing academic reports must retain at least two explicit project identity terms."
            ),
            "matched_tokens": hit_tokens,
            "severity": "hard",
        })
    return issues


def _check_paper_roadmap(state: ReportState, intro_content: str) -> list[dict]:
    """Soft-flag missing paper-roadmap sentence for non-admissions academic reports.

    Skipped for admissions_report (that mode intentionally strips academic
    boilerplate) and for non-academic profiles. Soft severity; this is a
    quality signal, not a hard gate.
    """
    issues: list[dict] = []
    profile = state.spec.get("report_profile", "")
    if profile != "academic_paper":
        return issues
    if any(re.search(p, intro_content, re.IGNORECASE) for p in _PAPER_ROADMAP_PATTERNS):
        return issues
    issues.append({
        "section": "introduction",
        "intrusion_type": "missing_paper_roadmap",
        "detail": (
            "Introduction has no paper-roadmap sentence "
            "(\"The remainder of this report is organized as follows ...\")."
        ),
        "severity": "soft",
    })
    return issues


def _check_abstract_claims(state: ReportState, abstract_content: str) -> list[dict]:
    """Verify abstract claims are backed by evidence."""
    issues = []

    # Extract claims from abstract (simplified - look for claim-like sentences)
    claim_pattern = re.compile(r'\b(show|demonstrate|indicate|suggest|prove|reveal)\b', re.IGNORECASE)
    abstract_claims = claim_pattern.findall(abstract_content)

    # Get claim IDs from claim matrix
    claim_matrix = state.plan.get("claim_matrix", {})
    valid_claims = {c.get("claim_id", "") for c in claim_matrix.get("claims", [])}

    # Check sentence map for abstract sentences
    sentence_map = _load_jsonl(state.drafts.get("sentence_map_path"))

    abstract_sents = [s for s in sentence_map if s.get("section_id") == "abstract"]

    # If abstract has claims but no sentence map entries, that's a problem
    if abstract_claims and not abstract_sents:
        issues.append({
            "section": "abstract",
            "intrusion_type": "unverifiable_claim",
            "detail": "Abstract contains claims but no sentence-to-claim mapping found",
            "severity": "soft",
        })

    return issues


def run_section_role_check(state: ReportState) -> ReportState:
    """T_NEW: SECTION_ROLE_CHECK - verify IMRaD section role separation.

    Position: before QA_GATE.
    """
    merged_path = state.drafts.get("merged_draft_md", "")
    if not merged_path or not Path(merged_path).exists():
        state.qa["section_role_report_path"] = ""
        return state

    merged_text = Path(merged_path).read_text(encoding="utf-8")
    section_map = _split_by_sections(merged_text)

    all_issues = []

    # Check Results section
    results_content = section_map.get("results", "")
    if results_content:
        all_issues.extend(_check_section("results", results_content, RESULTS_INTRUSION_PATTERNS))

    # Check Discussion section
    discussion_content = section_map.get("discussion", "")
    if discussion_content:
        all_issues.extend(_check_section("discussion", discussion_content, DISCUSSION_INTRUSION_PATTERNS))

    # Check Methods section
    methods_content = section_map.get("methods", "")
    if methods_content:
        all_issues.extend(_check_section("methods", methods_content, METHODS_INTRUSION_PATTERNS))

    # Check Introduction section
    intro_content = section_map.get("introduction", "")
    if intro_content:
        all_issues.extend(_check_section("introduction", intro_content, INTRODUCTION_INTRUSION_PATTERNS))
        all_issues.extend(_check_thesis_spine(state, intro_content))
        all_issues.extend(_check_paper_roadmap(state, intro_content))

    # Check Abstract claims
    abstract_content = section_map.get("abstract", "")
    if abstract_content:
        all_issues.extend(_check_abstract_claims(state, abstract_content))

    # Classify issues by severity
    hard_issues = [i for i in all_issues if i.get("severity") == "hard"]
    soft_issues = [i for i in all_issues if i.get("severity") == "soft"]

    report = {
        "job_id": state.job_id,
        "total_issues": len(all_issues),
        "hard_issues": len(hard_issues),
        "soft_issues": len(soft_issues),
        "issues": all_issues,
    }

    report_path = write_json_artifact(state, "section_role_report.json", report)
    state.qa["section_role_report_path"] = str(report_path)

    # Hard block per policy if role validation is required
    family = state.spec.get("report_profile", "academic_paper")
    if get_policy(family).claim.role_validation_required and hard_issues:
        from ..errors import QAHardBlockError
        reasons = [f"{i['section']}: {i['intrusion_type']}" for i in hard_issues[:5]]
        raise QAHardBlockError(f"Section role violations: {', '.join(reasons)}")

    return state
