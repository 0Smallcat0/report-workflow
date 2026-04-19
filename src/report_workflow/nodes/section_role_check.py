"""SECTION_ROLE_CHECK node - verify IMRaD section role separation.

Sits between CONSISTENCY_CHECK and QA_GATE in validate phase.

Validates that IMRaD sections maintain proper role boundaries:
  - Results: only presents findings (no interpretation)
  - Discussion: interprets results (no raw result restatement)
  - Methods: describes procedure (no conclusions)
  - Abstract: claims backed by正文
  - Introduction: no results

Output: section_role_report.json
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..runtime_support import write_json_artifact


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
    """Split merged markdown into section_id → content mapping."""
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


def _check_abstract_claims(state: ReportState, abstract_content: str) -> list[dict]:
    """Verify abstract claims are backed by正文."""
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

    Position: After CONSISTENCY_CHECK, before QA_GATE.
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

    # For academic_report, hard issues should block
    if state.spec.get("report_family") == "academic_report" and hard_issues:
        from ..errors import QAHardBlockError
        reasons = [f"{i['section']}: {i['intrusion_type']}" for i in hard_issues[:5]]
        raise QAHardBlockError(f"Section role violations: {', '.join(reasons)}")

    return state