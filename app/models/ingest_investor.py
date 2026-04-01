from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

InvestorType = Literal["vc", "cvc", "angel", "family_office", "grant", "accelerator", "other"]
InvestorStatus = Literal["active", "declined", "dormant", "new"]
EventType = Literal[
    "outreach", "meeting", "pitch", "follow_up", "decline",
    "re_engagement", "intro_via_third_party", "data_room_access", "term_sheet",
]
OutcomeType = Literal["pending", "interested", "rejected", "conditional", "timing_dependent"]
DeclineReason = Literal[
    "stage_mismatch", "thesis_mismatch", "portfolio_conflict",
    "no_clinical_data", "fund_timing", "prioritization", "team_mismatch",
    "differentiation_weak", "market_risk", "regulatory_risk", "valuation_mismatch",
]


# ── Request models ──────────────────────────────────────────────────────────

class IngestContactInput(BaseModel):
    name: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=100)


class IngestInteractionInput(BaseModel):
    event_date: date | None = None
    event_type: EventType
    summary: str = Field(min_length=1, max_length=5000)
    outcome: OutcomeType | None = None
    decline_reason: DeclineReason | None = None
    next_step: str | None = Field(default=None, max_length=2000)
    raw_segment: str | None = Field(default=None, max_length=10000)


class IngestInvestorInput(BaseModel):
    investor_name: str = Field(min_length=1, max_length=500)
    normalized_name: str = Field(min_length=1, max_length=500)
    normalized_domain: str | None = Field(default=None, max_length=500)
    investor_type: InvestorType = "vc"
    status: InvestorStatus
    reported_deal_size: str | None = Field(default=None, max_length=200)
    is_strategic: bool = False
    is_foundation: bool = False
    is_sovereign: bool = False
    is_crossover: bool = False
    internal_owner: str | None = Field(default=None, max_length=500)
    raw_notes: str | None = Field(default=None, max_length=50000)
    source_file: str | None = Field(default=None, max_length=500)


class IngestInvestorBundleRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    investor: IngestInvestorInput
    contacts: list[IngestContactInput] = Field(default_factory=list, max_length=20)
    interactions: list[IngestInteractionInput] = Field(default_factory=list, max_length=200)


# ── Response models ─────────────────────────────────────────────────────────

class IngestInvestorBundleResponse(BaseModel):
    client_investor_id: str
    investor_id: str | None
    needs_enrichment: bool
    contacts_upserted: int
    interactions_upserted: int


class InvestorGapResult(BaseModel):
    name: str
    normalized_name: str
    overall_score: int | None
    investor_type: str | None


class InvestorGapResponse(BaseModel):
    client_id: str
    gap_investors: list[InvestorGapResult]
    total: int
