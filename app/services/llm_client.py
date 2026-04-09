from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class LlmRetryExhaustedError(Exception):
    """Raised when _json_call cannot obtain valid JSON after the maximum retries.

    Carries the raw LLM text for held_for_review logging and response attachment.
    """

    def __init__(self, *, raw: str) -> None:
        self.raw = raw
        super().__init__(f"LLM returned invalid JSON after max retries. Preview: {raw[:200]}")


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
    avoid: str | None
    suggested_contact: str
    evidence_urls: list[str]
    confidence_score: float
    narrative_summary: str
    top_claims: list[str]


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


# ── Advisor prep dataclasses ────────────────────────────────────────────────

@dataclass(frozen=True)
class LlmAdvisorOutreachAngle:
    investor_name: str
    angle: str
    avoid: str
    re_engagement_notes: str | None


@dataclass(frozen=True)
class LlmAdvisorCallPlan:
    opening_framing: str
    discussion_threads: list[str]
    desired_outcome: str


@dataclass(frozen=True)
class LlmAdvisorObjection:
    objection: str
    response: str


@dataclass(frozen=True)
class LlmAdvisorPrep:
    key_insights: list[str]
    outreach_angles: list[LlmAdvisorOutreachAngle]
    call_plan: LlmAdvisorCallPlan
    likely_objections: list[LlmAdvisorObjection]
    risks_sensitivities: list[str]
    questions_to_ask: list[str]


@dataclass(frozen=True)
class LlmDigestResult:
    subject: str
    preheader: str
    sections: list[tuple[str, list[str]]]
    x_activity_section: LlmXActivitySection
    advisor_prep: LlmAdvisorPrep


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
        investor_firm: str | None,
        investor_thesis_keywords: list[str] | None,
        investor_portfolio_companies: list[str] | None,
        investor_key_partners: list[str] | None,
        client_name: str | None,
        client_thesis: str | None,
        client_geography: str | None,
        client_modality: str | None,
        client_keywords: list[str] | None,
        client_stage: str | None,
        grok_batch_context: str | None,
        x_engagement_replies: int | None,
        x_engagement_reposts: int | None,
        x_engagement_likes: int | None,
        x_engagement_is_original: bool | None,
        x_engagement_author: str | None,
        x_engagement_author_type: str | None,
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
        therapeutic_area: str | None,
        stage: str | None,
        target_raise: str | None,
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
