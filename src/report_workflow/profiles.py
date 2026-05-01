"""Report profile registry and inference helpers.

Profiles are the public report-shape contract. They replace the older
family/detail split with one semantic ID per report type.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReferenceTemplatePolicy:
    default_mode: str = "style_reference"
    fixed_template_prompt_markers: tuple[str, ...] = (
        "exact format",
        "exact cover",
        "same format",
        "same cover",
        "完全照格式",
        "完全照封面",
        "相同格式",
        "相同封面",
        "固定模板",
    )


@dataclass(frozen=True)
class ReportProfile:
    profile_id: str
    display_name: str
    blueprint_file: str
    policy_id: str
    aliases: tuple[str, ...] = ()
    description: str = ""
    evidence_backed_claims: bool = True
    section_contract_required: bool = True
    strictness: str = "medium"
    reference_template: ReferenceTemplatePolicy = field(default_factory=ReferenceTemplatePolicy)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reference_template"]["fixed_template_prompt_markers"] = list(
            self.reference_template.fixed_template_prompt_markers
        )
        return data


PROFILE_REGISTRY: dict[str, ReportProfile] = {
    "engineering_lab_report": ReportProfile(
        profile_id="engineering_lab_report",
        display_name="Engineering Lab Report",
        blueprint_file="engineering_lab_report.yaml",
        policy_id="engineering_lab_report",
        aliases=("engineering report", "lab report", "experiment report", "工程報告", "實驗報告"),
        description=(
            "Engineering experiment reports with requirement, unit, formula, "
            "calculation, figure/table, and Chinese render QA contracts."
        ),
        strictness="high",
    ),
    "academic_paper": ReportProfile(
        profile_id="academic_paper",
        display_name="Academic Paper",
        blueprint_file="academic_paper.yaml",
        policy_id="academic_paper",
        aliases=("academic report", "research paper", "學術報告", "研究論文"),
        strictness="high",
    ),
    "business_report": ReportProfile(
        profile_id="business_report",
        display_name="Business Report",
        blueprint_file="business_report.yaml",
        policy_id="business_report",
        aliases=("work report", "business", "business report", "工作報告", "商業報告"),
        strictness="medium",
    ),
    "proposal": ReportProfile(
        profile_id="proposal",
        display_name="Proposal",
        blueprint_file="proposal.yaml",
        policy_id="proposal",
        aliases=("proposal", "企劃書", "提案"),
        strictness="medium",
    ),
    "admissions_report": ReportProfile(
        profile_id="admissions_report",
        display_name="Admissions Report",
        blueprint_file="admissions_report.yaml",
        policy_id="admissions_report",
        aliases=("admissions", "graduate school", "application", "申請報告", "入學申請"),
        strictness="high",
    ),
    "admissions_project_report": ReportProfile(
        profile_id="admissions_project_report",
        display_name="Admissions Project Report",
        blueprint_file="admissions_project_report.yaml",
        policy_id="admissions_project_report",
        aliases=("admissions project report", "application project report", "申請專案"),
        strictness="medium",
    ),
    "custom": ReportProfile(
        profile_id="custom",
        display_name="Custom Report",
        blueprint_file="custom.yaml",
        policy_id="custom",
        aliases=("custom", "hybrid", "自訂", "其他"),
        strictness="medium",
    ),
}


PROFILE_IDS = tuple(PROFILE_REGISTRY)


def normalize_profile_id(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower().replace("-", "_").replace(" ", "_")
    if raw in PROFILE_REGISTRY:
        return raw
    for profile_id, profile in PROFILE_REGISTRY.items():
        aliases = {alias.lower().replace("-", "_").replace(" ", "_") for alias in profile.aliases}
        if raw in aliases:
            return profile_id
    return raw


def infer_report_profile(user_prompt: str) -> str:
    text = (user_prompt or "").lower()
    if any(
        token in text
        for token in ("工程報告", "實驗報告", "lab report", "experiment report", "engineering report")
    ):
        return "engineering_lab_report"
    if (
        any(token in text for token in ("admissions project", "application project", "申請專案"))
        or (
            any(token in text for token in ("admissions", "graduate school", "application", "申請"))
            and any(
                token in text
                for token in (
                    "project report",
                    "academic project",
                    "project introduction",
                    "internal architecture",
                    "專案",
                )
            )
        )
    ):
        return "admissions_project_report"
    if any(token in text for token in ("admissions", "graduate school", "application", "申請")):
        return "admissions_report"
    if any(token in text for token in ("proposal", "企劃書", "提案")):
        return "proposal"
    if any(
        token in text
        for token in (
            "work report",
            "business",
            "executive summary",
            "recommendation",
            "client report",
            "工作報告",
            "商業報告",
        )
    ):
        return "business_report"
    if "hybrid" in text or "custom" in text or "自訂" in text:
        return "custom"
    return "academic_paper"


def get_profile(profile_id: str | None = None) -> ReportProfile:
    normalized = normalize_profile_id(profile_id) or "academic_paper"
    if normalized not in PROFILE_REGISTRY:
        raise ValueError(f"Unknown report_profile={profile_id!r}. Known profiles: {list(PROFILE_REGISTRY)}")
    return PROFILE_REGISTRY[normalized]


def select_reference_template_mode(profile_id: str, user_prompt: str, requested_mode: str | None = None) -> str:
    if requested_mode:
        return requested_mode
    profile = get_profile(profile_id)
    text = (user_prompt or "").casefold()
    if any(marker.casefold() in text for marker in profile.reference_template.fixed_template_prompt_markers):
        return "fixed_template"
    return profile.reference_template.default_mode
