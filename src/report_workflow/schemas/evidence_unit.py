"""EvidenceUnit schema."""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class EvidenceUnit(BaseModel):
    evidence_id: str
    source_id: str
    granularity: Literal["sentence", "paragraph", "table_row", "figure"]
    evidence_type: Literal["quantitative", "qualitative", "methodological", "contextual"]
    content: str
    provenance_score: float = Field(ge=0.0, le=1.0)
    evidence_grade: Literal["high", "medium", "low"]
    allowed_claim_types: list[str]
    block_id: Optional[str] = None
    page_number: Optional[int] = None
    requires_hedged_wording: bool = False
    first_hand_account: bool = False
    contains_methodology: bool = False
    contains_citations: bool = False
    claimed_reproducibility: bool = False
