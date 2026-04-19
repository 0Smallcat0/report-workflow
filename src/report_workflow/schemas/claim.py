"""Claim schema."""
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class ClaimType(str, Enum):
    FACTUAL = "factual"
    STATISTICAL = "statistical"
    METHODOLOGICAL = "methodological"
    REGULATORY = "regulatory"
    QUALITATIVE = "qualitative"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"


class Claim(BaseModel):
    claim_id: str
    section_id: str
    claim_text: str
    evidence_ids: list[str]
    claim_type: ClaimType
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    status: ClaimStatus = Field(default=ClaimStatus.UNVERIFIED)
    provenance_min: float = 0.0
    requires_hedged_wording: bool = False


class ClaimMatrix(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
