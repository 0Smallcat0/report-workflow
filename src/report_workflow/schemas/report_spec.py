"""ReportSpec schema."""
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class TaskIntent(str, Enum):
    NEW_DRAFT = "new_draft"
    REVISE_EXISTING = "revise_existing"
    QA_FIX = "qa_fix"
    REVIEWER_RESPONSE = "reviewer_response"


class ArtifactRole(str, Enum):
    SOURCE_DATA = "source_data"
    EXISTING_DRAFT = "existing_draft"
    GUIDELINES = "guidelines"
    SUPPLEMENTARY = "supplementary"


class ReportProfile(str, Enum):
    ENGINEERING_LAB_REPORT = "engineering_lab_report"
    ACADEMIC_PAPER = "academic_paper"
    BUSINESS_REPORT = "business_report"
    PROPOSAL = "proposal"
    ADMISSIONS_REPORT = "admissions_report"
    ADMISSIONS_PROJECT_REPORT = "admissions_project_report"
    CUSTOM = "custom"


class DeliveryMode(str, Enum):
    FRESH_DOC = "fresh_doc"
    TRACKED_REVIEW = "tracked_review"
    RESPONSE_TO_REVIEWERS = "response_to_reviewers"


class Audience(str, Enum):
    EXPERT = "expert"
    GENERAL = "general"
    REGULATORY = "regulatory"


class CitationStyle(str, Enum):
    APA = "apa"
    MLA = "mla"
    CHICAGO = "chicago"
    IEEE = "ieee"


class ReportSpec(BaseModel):
    task_intent: TaskIntent = Field(default=TaskIntent.NEW_DRAFT)
    report_profile: ReportProfile = Field(default=ReportProfile.ACADEMIC_PAPER)
    delivery_mode: DeliveryMode = Field(default=DeliveryMode.FRESH_DOC)
    audience: Audience = Field(default=Audience.EXPERT)
    citation_style: CitationStyle = Field(default=CitationStyle.APA)
    artifact_role_map: dict[str, ArtifactRole] = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    revision_base_path: Optional[str] = None
    selected_guidelines: list[str] = Field(default_factory=list)
