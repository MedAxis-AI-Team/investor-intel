from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.config import DEFAULT_SCHEMA_VERSION
from app.models.common import Confidence
from app.models.ingest_investor import EventType, OutcomeType

PipelineStatus = Literal[
    "uncontacted",
    "outreach_sent",
    "meeting_scheduled",
    "active_dialogue",
    "passed",
    "committed",
]

InvestorSource = Literal["discovery", "client_provided"]
InvestorTier = Literal["Tier 1", "Tier 2", "Below Threshold"]
DimensionLevel = Literal["High", "Medium", "Low"]
InvestorType = Literal["vc", "cvc", "angel", "family_office", "grant", "accelerator", "other"]


class ClientProfile(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    thesis: str = Field(min_length=1, max_length=4000)
    geography: str | None = Field(default=None, max_length=200)
    funding_target: str | None = Field(default=None, max_length=50)
    competitor_watchlist: list[str] = Field(default_factory=list, max_length=10)


class InvestorInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)
    pipeline_status: PipelineStatus | None = Field(default=None)
    investor_type: InvestorType | None = Field(default=None)


class ScoreInvestorsRequest(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    client: ClientProfile
    investors: list[InvestorInput] = Field(min_length=1, max_length=50)
    client_id: str | None = Field(default=None, max_length=200)


# ── Raw axis breakdown (internal only) ─────────────────────────────────────

class InvestorScoreBreakdown(BaseModel):
    thesis_alignment: int = Field(ge=0, le=100)
    stage_fit: int = Field(ge=0, le=100)
    check_size_fit: int = Field(ge=0, le=100)
    scientific_regulatory_fit: int | None = Field(default=None, ge=0, le=100)
    recency: int = Field(ge=0, le=100)
    geography: int = Field(ge=0, le=100)


# ── Client-facing score ─────────────────────────────────────────────────────

class DimensionStrengths(BaseModel):
    strategic_fit: DimensionLevel
    stage_relevance: DimensionLevel
    capital_alignment: DimensionLevel
    scientific_depth: DimensionLevel | None  # null when scientific_regulatory_fit not scored
    market_activity: DimensionLevel
    geographic_proximity: DimensionLevel


class InvestorInteractionBrief(BaseModel):
    date: date | None
    event_type: EventType
    summary: str
    outcome: OutcomeType | None


class InvestorScore(BaseModel):
    investor: InvestorInput
    composite_score: int = Field(ge=0, le=100)
    investor_tier: InvestorTier
    investor_source: InvestorSource
    confidence: Confidence
    suggested_contact: str = Field(max_length=200)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)
    dimension_strengths: DimensionStrengths
    narrative_summary: str = Field(max_length=2000)
    top_claims: list[str] = Field(default_factory=list, max_length=5)
    interactions: list[InvestorInteractionBrief] = Field(default_factory=list, max_length=50)


# ── Internal advisor score ──────────────────────────────────────────────────

class InvestorAdvisorScore(BaseModel):
    investor_name: str
    outreach_angle: str = Field(max_length=2000)
    avoid: str | None = Field(default=None, max_length=1000)
    re_engagement_notes: str | None = Field(default=None, max_length=2000)
    full_axis_breakdown: InvestorScoreBreakdown
    notes: str | None = Field(default=None, max_length=2000)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)


# ── Response ────────────────────────────────────────────────────────────────

class ScoreInvestorsResponse(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    results: list[InvestorScore]
    advisor_data: list[InvestorAdvisorScore]
