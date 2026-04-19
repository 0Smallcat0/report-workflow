"""PolicyPack — unified family-specific policy interface for report_workflow.

Design: Config Wrapper approach. Each policy class loads its data from existing
config files (no duplication of data). Nodes call policy.xxx instead of
if report_family == "...".

Usage in nodes:
    from ..policies import get_policy
    policy = get_policy(state.spec.get("report_family", "academic_report"))
    if policy.front_matter.required:
        ...
"""
import importlib.resources
import json
from dataclasses import dataclass, field
from typing import Optional


# ------------------------------------------------------------------
# Policy sub-objects (dataclasses with typed fields)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class FrontMatterPolicy:
    required: bool
    placeholder_blocked: bool
    author_block_required: bool
    auto_populate_missing_fields: bool  # academic=true: auto-fill from user_prompt


@dataclass(frozen=True)
class AbstractPolicy:
    word_count_min: int
    word_count_max: int
    structure_required: bool


@dataclass(frozen=True)
class CitationPolicy:
    style: str  # "APA" or "none"
    source_marker_hard_block: bool
    draft_prefer_marker_stripped: bool  # prefer publication_draft_md over publication_style_draft


@dataclass(frozen=True)
class ReferencePolicy:
    doi_verification_required: bool
    arxiv_verification_required: bool


@dataclass(frozen=True)
class FigurePolicy:
    audit_table_hard_block: bool
    figure_contract_required: bool


@dataclass(frozen=True)
class ResultsPolicy:
    empirical_strict: bool
    architectural_allowed: bool


@dataclass(frozen=True)
class ClaimPolicy:
    primary_source_required: bool
    role_validation_required: bool
    thesis_required: bool  # academic reports require thesis in outline
    rqs_required: bool  # academic reports may require research questions


@dataclass(frozen=True)
class GuidelinePolicy:
    hard_guideline_ids: list[str]
    auto_select_allowed: bool  # academic=false (require explicit --guidelines)


@dataclass
class ReportPolicy:
    """Base class for report family policies.

    Each concrete subclass hard-codes the family-specific values.
    Config data is loaded from existing config files at __init__ time.
    """
    front_matter: FrontMatterPolicy
    abstract: AbstractPolicy
    citation: CitationPolicy
    reference: ReferencePolicy
    figure: FigurePolicy
    results: ResultsPolicy
    claim: ClaimPolicy
    guideline: GuidelinePolicy
    banned_phrases: list[str] = field(default_factory=list)

    def load_banned_phrases(self, family: str) -> list[str]:
        """Load banned phrases for the given family alias from configs/banned_phrases.json.

        Args:
            family: "academic", "work", or "hybrid" (not the full "academic_report" name)
        """
        try:
            with importlib.resources.as_file(
                importlib.resources.files("report_workflow") / "configs" / "banned_phrases.json"
            ) as path:
                if path.exists():
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    return data.get(family, data.get("academic", []))
        except Exception:
            pass
        return []

    def load_hard_guidelines(self, family: str) -> list[str]:
        """Load hard-block guideline IDs for the given family alias."""
        try:
            with importlib.resources.as_file(
                importlib.resources.files("report_workflow") / "configs" / "guideline_severity_policy.json"
            ) as path:
                if path.exists():
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    return data.get("hard", {}).get(family, [])
        except Exception:
            pass
        return []


# ------------------------------------------------------------------
# Concrete policy classes
# ------------------------------------------------------------------

class AcademicReportPolicy(ReportPolicy):
    def __init__(self):
        phrases = self.load_banned_phrases("academic")
        hard_ids = self.load_hard_guidelines("academic")

        super().__init__(
            front_matter=FrontMatterPolicy(
                required=True,
                placeholder_blocked=True,
                author_block_required=True,
                auto_populate_missing_fields=True,
            ),
            abstract=AbstractPolicy(
                word_count_min=180,
                word_count_max=220,
                structure_required=True,
            ),
            citation=CitationPolicy(
                style="APA",
                source_marker_hard_block=True,
                draft_prefer_marker_stripped=True,
            ),
            reference=ReferencePolicy(
                doi_verification_required=True,
                arxiv_verification_required=True,
            ),
            figure=FigurePolicy(
                audit_table_hard_block=True,
                figure_contract_required=True,
            ),
            results=ResultsPolicy(
                empirical_strict=True,
                architectural_allowed=True,
            ),
            claim=ClaimPolicy(
                primary_source_required=True,
                role_validation_required=True,
                thesis_required=True,
                rqs_required=False,
            ),
            guideline=GuidelinePolicy(hard_guideline_ids=hard_ids, auto_select_allowed=False),
            banned_phrases=phrases,
        )


class WorkReportPolicy(ReportPolicy):
    def __init__(self):
        phrases = self.load_banned_phrases("work")
        hard_ids = self.load_hard_guidelines("work")

        super().__init__(
            front_matter=FrontMatterPolicy(
                required=False,
                placeholder_blocked=True,
                author_block_required=False,
                auto_populate_missing_fields=False,
            ),
            abstract=AbstractPolicy(
                word_count_min=100,
                word_count_max=200,
                structure_required=False,
            ),
            citation=CitationPolicy(
                style="none",
                source_marker_hard_block=False,
                draft_prefer_marker_stripped=False,
            ),
            reference=ReferencePolicy(
                doi_verification_required=False,
                arxiv_verification_required=False,
            ),
            figure=FigurePolicy(
                audit_table_hard_block=False,
                figure_contract_required=False,
            ),
            results=ResultsPolicy(
                empirical_strict=False,
                architectural_allowed=True,
            ),
            claim=ClaimPolicy(
                primary_source_required=False,
                role_validation_required=False,
                thesis_required=False,
                rqs_required=False,
            ),
            guideline=GuidelinePolicy(hard_guideline_ids=hard_ids, auto_select_allowed=True),
            banned_phrases=phrases,
        )


class HybridReportPolicy(ReportPolicy):
    def __init__(self):
        phrases = self.load_banned_phrases("hybrid")
        hard_ids = self.load_hard_guidelines("hybrid")

        super().__init__(
            front_matter=FrontMatterPolicy(
                required=False,
                placeholder_blocked=True,
                author_block_required=False,
                auto_populate_missing_fields=False,
            ),
            abstract=AbstractPolicy(
                word_count_min=150,
                word_count_max=250,
                structure_required=False,
            ),
            citation=CitationPolicy(
                style="APA",
                source_marker_hard_block=True,
                draft_prefer_marker_stripped=False,
            ),
            reference=ReferencePolicy(
                doi_verification_required=True,
                arxiv_verification_required=False,
            ),
            figure=FigurePolicy(
                audit_table_hard_block=False,
                figure_contract_required=False,
            ),
            results=ResultsPolicy(
                empirical_strict=False,
                architectural_allowed=True,
            ),
            claim=ClaimPolicy(
                primary_source_required=False,
                role_validation_required=False,
                thesis_required=False,
                rqs_required=False,
            ),
            guideline=GuidelinePolicy(hard_guideline_ids=hard_ids, auto_select_allowed=True),
            banned_phrases=phrases,
        )


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

_POLICY_REGISTRY: dict[str, type[ReportPolicy]] = {
    "academic_report": AcademicReportPolicy,
    "work_report": WorkReportPolicy,
    "hybrid_report": HybridReportPolicy,
}

_POLICY_CACHE: dict[str, ReportPolicy] = {}


def get_policy(family: Optional[str] = None) -> ReportPolicy:
    """Return the ReportPolicy singleton for the given family.

    Args:
        family: "academic_report", "work_report", or "hybrid_report".
                 Defaults to "academic_report" if None.

    Returns:
        The corresponding ReportPolicy singleton.

    Raises:
        ValueError: If family is not a known report family.
    """
    if family is None:
        family = "academic_report"

    if family not in _POLICY_REGISTRY:
        raise ValueError(
            f"Unknown report_family={family!r}. "
            f"Known families: {list(_POLICY_REGISTRY.keys())}"
        )

    if family not in _POLICY_CACHE:
        _POLICY_CACHE[family] = _POLICY_REGISTRY[family]()

    return _POLICY_CACHE[family]
