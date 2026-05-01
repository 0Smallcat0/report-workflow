"""SECTION_DRAFT writer prompt."""

WRITER_SYSTEM_PROMPT = """You are an expert scientific and technical report writer.

Given an outline, claim matrix, and evidence, write precise, evidence-bound prose for each section.

## Rules
1. NEVER generate a claim not in the claim_matrix
2. Apply hedged wording where requires_hedged_wording=true
3. Bind each claim to its evidence_ids via inline citations in format [CITE:cite_id]
4. Write in formal academic/work style
5. Each section should be self-contained but coherent with other sections
6. Do not invent data or claims - only use provided evidence
7. For admissions-facing reports, prefer a project monograph voice over a journal-template voice

## Output Format
Return a JSON object:
{
  "sections": {
    "section_id": {
      "content": "# Section Title\n\nProse content...",
      "sentences": [
        {
          "sentence_text": "The sentence text.",
          "claim_ids": ["claim_id"],
          "evidence_ids": ["evidence_id"],
          "citation_ids": ["cite_id"],
          "wording_strength": "strong" | "hedged" | "weak"
        }
      ]
    }
  }
}

## Section Writing Guidelines
- abstract: brief summary, 150-250 words
- introduction: background, objectives, scope
- methods: describe methodology used
- results: present findings bound to evidence
- discussion: interpret results, limitations
- conclusion: summarize key points
- recommendations: actionable items based on findings"""

WRITER_USER_PROMPT_TEMPLATE = """## Outline
{outline_json}

## Claim Matrix
{claim_matrix_json}

## Evidence Ledger (top evidence per claim)
{evidence_summary}

## Task
Write the prose for each section using the outline and evidence provided. Output the section content with sentence-level mapping."""

import json


def get_writer_user_prompt(
    outline: dict,
    claim_matrix: dict,
    evidence_ledger: list[dict],
    report_profile: str = "",
) -> str:
    evidence_str = json.dumps(evidence_ledger, indent=2)
    if len(evidence_str) > 5000:
        evidence_str = evidence_str[:5000] + "\n... [EVIDENCE TRUNCATED; may exceed context limit]"
    prompt = WRITER_USER_PROMPT_TEMPLATE.format(
        outline_json=json.dumps(outline, indent=2),
        claim_matrix_json=json.dumps(claim_matrix, indent=2),
        evidence_summary=evidence_str
    )
    if report_profile == "admissions_report":
        prompt += (
            "\n\n## Admissions-facing narrative guidance\n"
            "- Write for reviewers evaluating research ability and project judgment.\n"
            "- Make the research problem, design choice, and significance progression explicit.\n"
            "- Keep deterministic compilation / StrategyIR / AST / quality gates as the spine.\n"
            "- Keep LLM modules subordinate and constrained.\n"
            "- Avoid journal-template scaffolding such as 'The remainder of this paper is organized as follows'.\n"
        )
    return prompt


def get_writer_system_prompt() -> str:
    return WRITER_SYSTEM_PROMPT
