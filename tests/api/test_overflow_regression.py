"""Regression tests: oversized LLM output must not cause HTTP 500.

These tests inject an LlmClient that returns strings longer than the Pydantic
field max_length limits. The service truncation layer (anthropic_client.py)
must cap the values before model construction, so every call should return 200.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import (
    LlmAdvisorCallPlan,
    LlmAdvisorPrep,
    LlmDigestResult,
    LlmGrantScore,
    LlmSignalAnalysis,
    LlmSignalBriefing,
    LlmXActivitySection,
)

_HUGE = "x" * 10_000


class _OversizeLlmClient:
    """Returns strings far beyond every field max_length."""

    async def score_investor(self, **_):
        from app.services.llm_client import LlmInvestorScore
        return LlmInvestorScore(
            thesis_alignment=80, stage_fit=70, check_size_fit=60,
            scientific_regulatory_fit=None, recency=65, geography=50,
            notes=_HUGE, outreach_angle=_HUGE, avoid=_HUGE,
            suggested_contact="Not identified",
            evidence_urls=[], confidence_score=0.9,
            narrative_summary=_HUGE, top_claims=[_HUGE, _HUGE],
        )

    async def analyze_signal(self, *, signal_type, title, url, published_at, **_):
        from app.services._llm_normalizers import compute_expiry
        return LlmSignalAnalysis(
            priority="HIGH",
            rationale=_HUGE,
            categories=[signal_type],
            evidence_urls=[url],
            confidence_score=0.85,
            relevance_score=75,
            briefing=LlmSignalBriefing(
                headline=_HUGE,
                why_it_matters=_HUGE,
                outreach_angle=_HUGE,
                suggested_contact="Not identified",
                time_sensitivity=_HUGE,
                source_urls=[url],
            ),
            signal_type="fund_close",
            expires_relevance=compute_expiry("fund_close", published_at),
            x_signal_type=None,
        )

    async def generate_digest(self, *, client_name, week_start, week_end, **_):
        return LlmDigestResult(
            subject=_HUGE,
            preheader=_HUGE,
            sections=[(_HUGE, [_HUGE, _HUGE])],
            x_activity_section=LlmXActivitySection(
                signals=[], section_note="No X signals recorded this week."
            ),
            advisor_prep=LlmAdvisorPrep(
                key_insights=["Key insight"],
                outreach_angles=[],
                call_plan=LlmAdvisorCallPlan(
                    opening_framing=_HUGE,
                    discussion_threads=["Thread one"],
                    desired_outcome=_HUGE,
                ),
                likely_objections=[],
                risks_sensitivities=[],
                questions_to_ask=[],
            ),
        )

    async def score_grant(self, *, company_name, **_):
        return LlmGrantScore(
            overall_score=85,
            therapeutic_match=90,
            stage_eligibility=85,
            award_size_relevance=80,
            deadline_feasibility=88,
            historical_funding=75,
            rationale=_HUGE,
            application_guidance=_HUGE,
            confidence="high",
        )


@pytest.fixture()
def oversize_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _OversizeLlmClient()
    return TestClient(app)


def test_analyze_signal_oversized_fields_no_500(oversize_client) -> None:
    res = oversize_client.post(
        "/analyze-signal",
        json={
            "signal_type": "SEC_EDGAR",
            "title": "Form D filed",
            "url": "https://www.sec.gov/example",
            "raw_text": _HUGE,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    briefing = body["data"]["analysis"]["briefing"]
    assert len(briefing["headline"]) <= 300
    assert len(briefing["why_it_matters"]) <= 1000
    assert len(briefing["outreach_angle"]) <= 1000
    assert len(briefing["time_sensitivity"]) <= 200


def test_generate_digest_oversized_fields_no_500(oversize_client) -> None:
    res = oversize_client.post(
        "/generate-digest",
        json={
            "client": {"name": "NovaBio"},
            "week_start": "2026-04-14",
            "week_end": "2026-04-20",
            "signals": [{"title": "Signal A", "url": "https://example.com"}],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    digest = body["data"]["client_digest"]
    assert len(digest["subject"]) <= 200
    assert len(digest["preheader"]) <= 300


def test_score_grants_oversized_fields_no_500(oversize_client) -> None:
    res = oversize_client.post(
        "/score-grants",
        json={
            "client_profile": {
                "company_name": "NovaBio",
                "therapeutic_area": "Oncology",
                "stage": "Phase 2",
                "keywords": ["cancer"],
            },
            "grants": [
                {
                    "source": "NIH",
                    "title": "SBIR Phase II",
                    "agency": "NCI",
                    "url": "https://grants.nih.gov/example",
                }
            ],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    scored = body["data"]["scored_grants"][0]
    assert len(scored["rationale"]) <= 4000
    if scored.get("application_guidance"):
        assert len(scored["application_guidance"]) <= 4000
