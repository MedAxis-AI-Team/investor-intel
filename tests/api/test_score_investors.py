from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import LlmInvestorScore

def test_score_investors_returns_batch_results(client) -> None:
    res = client.post(
        "/score-investors",
        json={
            "client": {"name": "NovaBio", "thesis": "Diagnostics"},
            "investors": [{"name": "Firm A"}, {"name": "Firm B"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    results = body["data"]["results"]
    assert results[0]["investor"]["name"] == "Firm A"
    assert results[1]["investor"]["name"] == "Firm B"
    assert results[0]["confidence"]["tier"] in {"HIGH", "MEDIUM", "LOW"}
    # 6-axis breakdown fields
    breakdown = results[0]["breakdown"]
    assert "thesis_alignment" in breakdown
    assert "stage_fit" in breakdown
    assert "check_size_fit" in breakdown
    assert "recency" in breakdown
    assert "geography" in breakdown
    # New required response fields
    assert results[0]["outreach_angle"]
    assert results[0]["suggested_contact"]


def test_score_investors_penalizes_missing_evidence(monkeypatch) -> None:
    class _NoEvidenceLlm:
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
            return LlmInvestorScore(
                thesis_alignment=80,
                stage_fit=70,
                check_size_fit=60,
                scientific_regulatory_fit=55,
                recency=65,
                geography=50,
                notes=None,
                outreach_angle="Generic outreach.",
                suggested_contact="Partner",
                evidence_urls=[],
                confidence_score=0.8,
            )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _NoEvidenceLlm()
    client = TestClient(app)

    res = client.post(
        "/score-investors",
        json={"client": {"name": "Acme", "thesis": "Bio"}, "investors": [{"name": "Firm A"}]},
    )
    assert res.status_code == 200
    body = res.json()
    confidence = body["data"]["results"][0]["confidence"]
    assert confidence["score"] <= 0.6


def test_score_investors_with_funding_target(client) -> None:
    res = client.post(
        "/score-investors",
        json={
            "client": {"name": "NovaBio", "thesis": "Diagnostics", "funding_target": "$5M Series A"},
            "investors": [{"name": "Firm A"}],
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_score_investors_null_scientific_regulatory_fit(monkeypatch) -> None:
    class _NullSciRegLlm:
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
            return LlmInvestorScore(
                thesis_alignment=80,
                stage_fit=70,
                check_size_fit=60,
                scientific_regulatory_fit=None,
                recency=65,
                geography=50,
                notes=None,
                outreach_angle="Outreach angle.",
                suggested_contact="Partner",
                evidence_urls=["https://example.com/ev"],
                confidence_score=0.9,
            )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _NullSciRegLlm()
    client = TestClient(app)

    res = client.post(
        "/score-investors",
        json={"client": {"name": "Acme", "thesis": "Bio"}, "investors": [{"name": "Firm A"}]},
    )
    assert res.status_code == 200
    result = res.json()["data"]["results"][0]
    assert result["breakdown"]["scientific_regulatory_fit"] is None
    assert result["overall_score"] > 0
