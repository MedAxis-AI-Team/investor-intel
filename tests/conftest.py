from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import (
    LlmDigestResult,
    LlmGrantScore,
    LlmInvestorScore,
    LlmSignalAnalysis,
    LlmSignalBriefing,
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
    ) -> LlmInvestorScore:
        from app.services.anthropic_client import _needs_sci_reg
        _has_fda = _needs_sci_reg(client_thesis)
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
            suggested_contact="Not identified",
            evidence_urls=evidence,
            confidence_score=0.9,
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
        investor_thesis_keywords: list[str] | None,
        investor_portfolio_companies: list[str] | None,
        investor_key_partners: list[str] | None,
        client_name: str | None,
        client_thesis: str | None,
        client_geography: str | None,
    ) -> LlmSignalAnalysis:
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
                suggested_contact="Head of BD",
                time_sensitivity="Act within 1 week",
                source_urls=[url],
            ),
            signal_type="fund_close",
            expires_relevance="2026-04-05",
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
    ) -> LlmDigestResult:
        return LlmDigestResult(
            subject=f"Weekly Digest — {client_name}",
            preheader=f"Highlights for {week_start}–{week_end}",
            sections=[
                ("Market Pulse", ["Markets were active.", "Notable deals occurred."]),
                ("Signals", [f"{t} ({u})" for (t, u) in signals[:5]]),
            ],
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
