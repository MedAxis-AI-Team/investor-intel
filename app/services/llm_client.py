from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class LlmInvestorScore:
    thesis_alignment: int
    stage_fit: int
    check_size_fit: int
    scientific_regulatory_fit: int | None
    recency: int
    geography: int
    notes: str | None
    outreach_angle: str
    suggested_contact: str
    evidence_urls: list[str]
    confidence_score: float


@dataclass(frozen=True)
class LlmSignalBriefing:
    headline: str
    why_it_matters: str
    outreach_angle: str
    suggested_contact: str
    time_sensitivity: str
    source_urls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LlmSignalAnalysis:
    priority: str
    rationale: str
    categories: list[str]
    evidence_urls: list[str]
    confidence_score: float
    relevance_score: int
    briefing: LlmSignalBriefing
    signal_type: str
    expires_relevance: str
    x_signal_type: str | None = None


@dataclass(frozen=True)
class LlmXActivitySignal:
    investor_name: str
    firm: str
    signal_summary: str
    x_signal_type: str
    recommended_action: str
    window: str
    priority: str


@dataclass(frozen=True)
class LlmXActivitySection:
    signals: list[LlmXActivitySignal]
    section_note: str | None


@dataclass(frozen=True)
class LlmDigestResult:
    subject: str
    preheader: str
    sections: list[tuple[str, list[str]]]
    x_activity_section: LlmXActivitySection


@dataclass(frozen=True)
class LlmGrantScore:
    overall_score: int
    therapeutic_match: int
    stage_eligibility: int
    award_size_relevance: int
    deadline_feasibility: int
    historical_funding: int
    rationale: str
    application_guidance: str | None
    confidence: str  # "high" | "medium" | "low"


class LlmClient(Protocol):
    async def score_investor(
        self,
        *,
        client_name: str,
        client_thesis: str,
        client_geography: str | None,
        client_funding_target: str | None,
        investor_name: str,
        investor_notes: str | None,
    ) -> LlmInvestorScore:
        raise NotImplementedError

    async def analyze_signal(
        self,
        *,
        signal_type: str,
        title: str,
        url: str,
        published_at: str | None,
        raw_text: str | None,
        investor_name: str | None,
        investor_thesis_keywords: list[str] | None,
        investor_portfolio_companies: list[str] | None,
        investor_key_partners: list[str] | None,
        client_name: str | None,
        client_thesis: str | None,
        client_geography: str | None,
        client_modality: str | None,
        client_keywords: list[str] | None,
        grok_batch_context: str | None,
    ) -> LlmSignalAnalysis:
        raise NotImplementedError

    async def generate_digest(
        self,
        *,
        client_name: str,
        week_start: str,
        week_end: str,
        signals: list[tuple[str, str]],
        investors: list[tuple[str, str | None]],
        market_context: str | None,
        x_signals: list[dict] | None,
    ) -> LlmDigestResult:
        raise NotImplementedError

    async def score_grant(
        self,
        *,
        company_name: str,
        therapeutic_area: str,
        stage: str,
        fda_pathway: str | None,
        keywords: list[str],
        grant_title: str,
        grant_agency: str,
        grant_program: str | None,
        grant_description: str | None,
        grant_eligibility: str | None,
        grant_award_amount: str | None,
        grant_deadline: str | None,
    ) -> LlmGrantScore:
        raise NotImplementedError
