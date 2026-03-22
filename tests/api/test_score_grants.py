from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import LlmGrantScore


_VALID_REQUEST = {
    "client_profile": {
        "company_name": "NovaBio",
        "therapeutic_area": "Oncology",
        "stage": "Phase 2",
        "fda_pathway": "Breakthrough Therapy",
        "keywords": ["cancer", "immunotherapy"],
    },
    "grants": [
        {
            "source": "NIH",
            "title": "SBIR Phase II: Novel Cancer Immunotherapy",
            "agency": "National Cancer Institute",
            "program": "SBIR",
            "award_amount": "$1,500,000",
            "deadline": "2027-06-30",
            "description": "Funding for innovative cancer immunotherapy approaches.",
            "eligibility": "Small businesses with <500 employees",
            "url": "https://grants.nih.gov/example",
        },
        {
            "source": "DOD",
            "title": "CDMRP Breakthrough Award",
            "agency": "Department of Defense",
            "program": None,
            "award_amount": "$600,000",
            "deadline": None,
            "description": None,
            "eligibility": None,
            "url": "https://cdmrp.army.mil/example",
        },
    ],
}


def test_score_grants_returns_scored_results(client: TestClient) -> None:
    res = client.post("/score-grants", json=_VALID_REQUEST)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert "scored_grants" in data
    assert "summary" in data
    assert len(data["scored_grants"]) == 2


def test_score_grants_result_shape(client: TestClient) -> None:
    res = client.post("/score-grants", json=_VALID_REQUEST)
    assert res.status_code == 200
    grant = res.json()["data"]["scored_grants"][0]
    assert "title" in grant
    assert "overall_score" in grant
    assert "breakdown" in grant
    assert "confidence" in grant
    breakdown = grant["breakdown"]
    for key in ("therapeutic_match", "stage_eligibility", "award_size_relevance", "deadline_feasibility", "historical_funding"):
        assert key in breakdown
        assert 0 <= breakdown[key] <= 100


def test_score_grants_sorted_by_score_descending(client: TestClient) -> None:
    res = client.post("/score-grants", json=_VALID_REQUEST)
    assert res.status_code == 200
    grants = res.json()["data"]["scored_grants"]
    scores = [g["overall_score"] for g in grants]
    assert scores == sorted(scores, reverse=True)


def test_score_grants_computes_days_until_deadline(client: TestClient) -> None:
    res = client.post("/score-grants", json=_VALID_REQUEST)
    assert res.status_code == 200
    grants = res.json()["data"]["scored_grants"]
    # First grant has a deadline; second does not
    grant_with_deadline = next(g for g in grants if g["deadline"] is not None)
    grant_without_deadline = next(g for g in grants if g["deadline"] is None)
    assert grant_with_deadline["days_until_deadline"] is not None
    assert grant_without_deadline["days_until_deadline"] is None


def test_score_grants_rejects_empty_grants_list(client: TestClient) -> None:
    payload = {**_VALID_REQUEST, "grants": []}
    res = client.post("/score-grants", json=payload)
    assert res.status_code == 422


def test_score_grants_single_grant(client: TestClient) -> None:
    payload = {**_VALID_REQUEST, "grants": [_VALID_REQUEST["grants"][0]]}
    res = client.post("/score-grants", json=payload)
    assert res.status_code == 200
    assert len(res.json()["data"]["scored_grants"]) == 1


def test_score_grants_confidence_tier_valid(client: TestClient) -> None:
    res = client.post("/score-grants", json=_VALID_REQUEST)
    assert res.status_code == 200
    for grant in res.json()["data"]["scored_grants"]:
        assert grant["confidence"] in {"high", "medium", "low"}


def test_score_grants_missing_client_profile_returns_422(client: TestClient) -> None:
    payload = {"grants": _VALID_REQUEST["grants"]}
    res = client.post("/score-grants", json=payload)
    assert res.status_code == 422


def test_score_grants_custom_llm_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    class _HighScoreLlm:
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
                overall_score=99,
                therapeutic_match=99,
                stage_eligibility=99,
                award_size_relevance=99,
                deadline_feasibility=99,
                historical_funding=99,
                rationale="Perfect match.",
                application_guidance=None,
                confidence="high",
            )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _HighScoreLlm()
    tc = TestClient(app)

    res = tc.post("/score-grants", json=_VALID_REQUEST)
    assert res.status_code == 200
    for grant in res.json()["data"]["scored_grants"]:
        assert grant["overall_score"] == 99
