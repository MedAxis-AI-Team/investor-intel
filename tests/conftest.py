from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import (
    LlmAdvisorCallPlan,
    LlmAdvisorPrep,
    LlmDigestResult,
    LlmGrantScore,
    LlmInvestorScore,
    LlmSignalAnalysis,
    LlmSignalBriefing,
    LlmXActivitySection,
    LlmXActivitySignal,
)


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

    # Ensure FastAPI settings cache is not polluted across tests
    os.environ.pop("REQUEST_TIMEOUT_SECONDS", None)
    os.environ.pop("RATE_LIMIT_WINDOW_SECONDS", None)
    os.environ.pop("RATE_LIMIT_MAX_REQUESTS", None)

    get_settings.cache_clear()


class _FakeLlmClient:
    async def score_investor(
        self,
        *,
        client_name: str,
        client_thesis: str,
        client_geography: str | None,
        client_funding_target: str | None,
        investor_name: str,
        investor_notes: str | None,
        scoring_instructions=None,
    ) -> LlmInvestorScore:
        from app.services._llm_normalizers import needs_sci_reg
        # If scoring_instructions explicitly enables sci_reg scoring, always include it.
        # Otherwise fall back to thesis-text detection.
        if scoring_instructions is not None and scoring_instructions.score_scientific_regulatory:
            _has_fda = True
        else:
            _has_fda = needs_sci_reg(client_thesis)
        evidence = [f"https://example.com/{investor_name.replace(' ', '-').lower()}"]
        return LlmInvestorScore(
            thesis_alignment=80,
            stage_fit=70,
            check_size_fit=60,
            scientific_regulatory_fit=55 if _has_fda else None,
            recency=65,
            geography=50,
            notes=f"Scored {investor_name} for {client_name}.",
            outreach_angle=f"Reach out to {investor_name} about thesis alignment.",
            avoid=None,
            suggested_contact="Not identified",
            evidence_urls=evidence,
            confidence_score=0.9,
            narrative_summary=f"Strong fit for {client_name}.",
            top_claims=[f"Evidence supports {investor_name} thesis alignment."],
        )

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
        from app.services._llm_normalizers import compute_expiry

        x_sig_type: str | None = None
        if signal_type == "X_GROK":
            x_sig_type = "fund_activity"

        return LlmSignalAnalysis(
            priority="HIGH",
            rationale=f"High priority: {title}",
            categories=[signal_type],
            evidence_urls=[url],
            confidence_score=0.85,
            relevance_score=75,
            briefing=LlmSignalBriefing(
                headline=f"Signal: {title}",
                why_it_matters="Significant market movement detected.",
                outreach_angle="Leverage this signal for timely outreach.",
                suggested_contact="Not identified",
                time_sensitivity="Act within 1 week",
                source_urls=[url],
            ),
            signal_type="fund_close",
            expires_relevance=compute_expiry("fund_close", published_at),
            x_signal_type=x_sig_type,
        )

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
        x_activity_signals: list[LlmXActivitySignal] = []
        if x_signals:
            for sig in x_signals[:3]:
                x_activity_signals.append(LlmXActivitySignal(
                    investor_name=sig.get("investor_name", "Unknown Investor"),
                    firm=sig.get("firm", "Unknown Firm"),
                    signal_summary=sig.get("signal_summary", "Activity detected"),
                    x_signal_type="fund_activity",
                    recommended_action="Monitor for follow-up",
                    window="this_week",
                    priority="medium",
                ))

        x_note: str | None = (
            "No X signals recorded this week."
            if not x_activity_signals
            else f"{len(x_activity_signals)} signal(s) detected."
        )

        return LlmDigestResult(
            subject=f"Weekly Digest — {client_name}",
            preheader=f"Highlights for {week_start}–{week_end}",
            sections=[
                ("Market Pulse", ["Markets were active.", "Notable deals occurred."]),
                ("Signals", [f"{t} ({u})" for (t, u) in signals[:5]]),
            ],
            x_activity_section=LlmXActivitySection(
                signals=x_activity_signals,
                section_note=x_note,
            ),
            advisor_prep=LlmAdvisorPrep(
                key_insights=["Key insight for the week."],
                outreach_angles=[],
                call_plan=LlmAdvisorCallPlan(
                    opening_framing="Frame the conversation around recent signals.",
                    discussion_threads=["Funding environment", "Clinical milestones"],
                    desired_outcome="Schedule introductory call.",
                ),
                likely_objections=[],
                risks_sensitivities=[],
                questions_to_ask=["What is your current deal pipeline?"],
            ),
        )

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
        return LlmGrantScore(
            overall_score=85,
            therapeutic_match=90,
            stage_eligibility=85,
            award_size_relevance=80,
            deadline_feasibility=88,
            historical_funding=75,
            rationale=f"Strong match for {company_name} in {therapeutic_area}.",
            application_guidance="Reference recent funded projects in this space.",
            confidence="high",
        )


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _FakeLlmClient()
    return TestClient(app)
