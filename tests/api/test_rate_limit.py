from __future__ import annotations

import pytest

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import (
    LlmAdvisorCallPlan,
    LlmAdvisorPrep,
    LlmDigestResult,
    LlmInvestorScore,
    LlmSignalAnalysis,
    LlmSignalBriefing,
    LlmXActivitySection,
)


class _LocalFakeLlmClient:
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
        return LlmInvestorScore(
            thesis_alignment=80,
            stage_fit=70,
            check_size_fit=60,
            scientific_regulatory_fit=55,
            recency=65,
            geography=50,
            notes=None,
            outreach_angle="Outreach.",
            avoid=None,
            suggested_contact="Partner",
            evidence_urls=["https://example.com/evidence"],
            confidence_score=0.9,
            narrative_summary="Test summary.",
            top_claims=["Claim 1."],
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
        return LlmSignalAnalysis(
            priority="HIGH",
            rationale="x",
            categories=[],
            evidence_urls=[url],
            confidence_score=0.9,
            relevance_score=75,
            briefing=LlmSignalBriefing(
                headline="h", why_it_matters="w", outreach_angle="o",
                suggested_contact="s", time_sensitivity="t",
            ),
            signal_type="fund_close",
            expires_relevance="2026-04-05",
            x_signal_type=None,
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
        x_signals: list[dict] | None = None,
        therapeutic_area: str | None = None,
        stage: str | None = None,
        target_raise: str | None = None,
    ) -> LlmDigestResult:
        return LlmDigestResult(
            subject="x",
            preheader="y",
            sections=[("z", ["a"])],
            x_activity_section=LlmXActivitySection(signals=[], section_note=None),
            advisor_prep=LlmAdvisorPrep(
                key_insights=[],
                outreach_angles=[],
                call_plan=LlmAdvisorCallPlan(
                    opening_framing="f",
                    discussion_threads=[],
                    desired_outcome="d",
                ),
                likely_objections=[],
                risks_sensitivities=[],
                questions_to_ask=[],
            ),
        )


@pytest.fixture()
def rate_limited_client(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "2")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _LocalFakeLlmClient()
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_rate_limit_enforced(rate_limited_client) -> None:
    payload = {"client": {"name": "Acme", "thesis": "Bio"}, "investors": [{"name": "Firm A"}]}

    r1 = rate_limited_client.post("/score-investors", json=payload)
    r2 = rate_limited_client.post("/score-investors", json=payload)
    r3 = rate_limited_client.post("/score-investors", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
