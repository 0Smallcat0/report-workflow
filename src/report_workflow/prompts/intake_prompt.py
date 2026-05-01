"""INTAKE system and user prompt."""

INTAKE_SYSTEM_PROMPT = """You are an expert intake analyst for a report generation workflow.

Given a user's prompt and any uploaded files, classify the task intent and select appropriate settings.

## Output Format
Return a JSON object with these fields:
{
  "task_intent": "new_draft" | "revise_existing" | "qa_fix" | "reviewer_response",
  "report_profile": "engineering_lab_report" | "academic_paper" | "business_report" | "proposal" | "admissions_report" | "admissions_project_report" | "custom",
  "delivery_mode": "fresh_doc" | "tracked_review" | "response_to_reviewers",
  "audience": "expert" | "general" | "regulatory",
  "citation_style": "apa" | "mla" | "chicago" | "ieee",
  "artifact_role_map": {
    "filename1.ext": "source_data" | "existing_draft" | "guidelines" | "supplementary",
    ...
  },
  "report_profile_description": "string description",
  "keywords": ["keyword1", "keyword2", ...]
}

## Classification Rules
- task_intent: classify based on explicit request
  - "new_draft" if asking to create new report
  - "revise_existing" if asking to revise/review an existing document
  - "qa_fix" if asking to fix issues in a draft
  - "reviewer_response" if responding to reviewer comments
- report_profile: infer from keywords and context
  - "engineering_lab_report" for engineering or experiment reports, especially Chinese lab handout requirements
  - "academic_paper" for research papers, studies, scientific topics
  - "business_report" for business, industry, operational topics
  - "proposal" for proposed work, project plans, bids, or grant-style requests
  - "admissions_report" for admissions-facing narrative reports
  - "admissions_project_report" for admissions reports centered on a project or internal architecture
  - "custom" for mixed or user-defined structures
- delivery_mode: "fresh_doc" by default unless explicit revision request
- audience: infer from content and request phrasing
- citation_style: "apa" by default for academic, adjust per request

## Artifact Role Mapping
- "source_data" for data files (CSV, XLSX, JSON)
- "existing_draft" for draft documents (DOCX, MD)
- "guidelines" for guideline documents
- "supplementary" for supplementary materials

Be precise and infer from context when not explicitly stated."""

INTAKE_USER_PROMPT_TEMPLATE = """## User Request
{prompt}

## Uploaded Files
{uploaded_files}

## Task
Analyze the request and files above, then output the classification JSON."""


def get_intake_user_prompt(prompt: str, uploaded_files: list[str]) -> str:
    files_str = "\n".join(f"- {f}" for f in uploaded_files) if uploaded_files else "- (no files uploaded)"
    return INTAKE_USER_PROMPT_TEMPLATE.format(prompt=prompt, uploaded_files=files_str)


def get_intake_system_prompt() -> str:
    return INTAKE_SYSTEM_PROMPT
