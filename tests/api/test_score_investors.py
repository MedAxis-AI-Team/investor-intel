from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import LlmInvestorScore

def test_score_investors_returns_batch_results(client) -> None:
    res = client.post(
        "/score-investors",
        headers={"X-API-Key": "test-api-key"},
        json={
            "client": {"name": "NovaBio", "thesis": "Diagnostics"},
            "investors": [{"name": "Firm A"}, {"name": "Firm B"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["results"][0]["investor"]["name"] == "Firm A"
    assert body["data"]["results"][1]["investor"]["name"] == "Firm B"
    assert body["data"]["results"][0]["confidence"]["tier"] in {"HIGH", "MEDIUM", "LOW"}


def test_score_investors_penalizes_missing_evidence(monkeypatch) -> None:
    class _NoEvidenceLlm:
        async def score_investor(self, *, client_name: str, client_thesis: str, investor_name: str) -> LlmInvestorScore:
            return LlmInvestorScore(
                thesis_alignment=80,
                stage_fit=70,
                check_size_fit=60,
                strategic_value=50,
                notes=None,
                evidence_urls=[],
                confidence_score=0.8,
            )

    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _NoEvidenceLlm()
    client = TestClient(app)

    res = client.post(
        "/score-investors",
        headers={"X-API-Key": "test-api-key"},
        json={"client": {"name": "Acme", "thesis": "Bio"}, "investors": [{"name": "Firm A"}]},
    )
    assert res.status_code == 200
    body = res.json()
    confidence = body["data"]["results"][0]["confidence"]
    assert confidence["score"] <= 0.6
