from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import DEFAULT_SCHEMA_VERSION
from app.models.common import Confidence


class ClientProfile(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    thesis: str = Field(min_length=1, max_length=4000)
    geography: str | None = Field(default=None, max_length=200)


class InvestorInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class ScoreInvestorsRequest(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    client: ClientProfile
    investors: list[InvestorInput] = Field(min_length=1, max_length=50)


class InvestorScoreBreakdown(BaseModel):
    thesis_alignment: int = Field(ge=0, le=100)
    stage_fit: int = Field(ge=0, le=100)
    check_size_fit: int = Field(ge=0, le=100)
    strategic_value: int = Field(ge=0, le=100)


class InvestorScore(BaseModel):
    investor: InvestorInput
    overall_score: int = Field(ge=0, le=100)
    confidence: Confidence
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)
    breakdown: InvestorScoreBreakdown
    notes: str | None = Field(default=None, max_length=2000)


class ScoreInvestorsResponse(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    results: list[InvestorScore]
