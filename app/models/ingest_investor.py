from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

InvestorType = Literal["vc", "cvc", "angel", "family_office", "grant", "accelerator", "other"]
RelationshipStatus = Literal["active", "declined", "dormant", "new"]
InteractionType = Literal[
    "outreach", "meeting", "pitch", "follow_up", "decline",
    "re_engagement", "intro_via_third_party", "data_room_access", "term_sheet",
]
# Alias kept for backwards-compat with score_investors imports
EventType = InteractionType
OutcomeType = Literal["pending", "interested", "rejected", "conditional", "timing_dependent"]
DeclineReason = Literal[
    "stage_mismatch", "thesis_mismatch", "portfolio_conflict",
    "no_clinical_data", "fund_timing", "prioritization", "team_mismatch",
    "differentiation_weak", "market_risk", "regulatory_risk", "valuation_mismatch",
]


# ── Request models ──────────────────────────────────────────────────────────

class IngestContactInput(BaseModel):
    full_name: str | None = Field(default=None, max_length=500)
    first_name: str | None = Field(default=None, max_length=200)
    last_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    linkedin_url: str | None = Field(default=None, max_length=500)


class IngestInteractionInput(BaseModel):
    interaction_date: date | None = None
    interaction_type: InteractionType
    summary: str = Field(min_length=1, max_length=5000)
    outcome: OutcomeType | None = None
    decline_reason: DeclineReason | None = None
    next_steps: str | None = Field(default=None, max_length=2000)
    raw_note_excerpt: str | None = Field(default=None, max_length=10000)


class IngestInvestorInput(BaseModel):
    firm_name: str = Field(min_length=1, max_length=500)
    investor_name: str | None = Field(default=None, max_length=500)
    investor_type: InvestorType = "vc"
    relationship_status: RelationshipStatus | None = None
    website: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=50000)


class IngestInvestorBundleRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    investor: IngestInvestorInput
    contacts: list[IngestContactInput] = Field(default_factory=list, max_length=20)
    interactions: list[IngestInteractionInput] = Field(default_factory=list, max_length=200)


# ── Response models ─────────────────────────────────────────────────────────

class IngestInvestorBundleResponse(BaseModel):
    client_investor_id: str
    investor_id: str | None
    contacts_upserted: int
    interactions_upserted: int


class InvestorGapResult(BaseModel):
    firm_name: str
    overall_score: int | None
    investor_type: str | None


class InvestorGapResponse(BaseModel):
    client_id: str
    gap_investors: list[InvestorGapResult]
    total: int
