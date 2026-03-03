from __future__ import annotations

import pytest

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import LlmDigestResult, LlmInvestorScore, LlmSignalAnalysis


class _LocalFakeLlmClient:
    async def score_investor(self, *, client_name: str, client_thesis: str, investor_name: str) -> LlmInvestorScore:
        return LlmInvestorScore(
            thesis_alignment=80,
            stage_fit=70,
            check_size_fit=60,
            strategic_value=50,
            notes=None,
            evidence_urls=["https://example.com/evidence"],
            confidence_score=0.9,
        )

    async def analyze_signal(self, *, signal_type: str, title: str, url: str, raw_text: str | None) -> LlmSignalAnalysis:
        return LlmSignalAnalysis(
            priority="HIGH",
            rationale="x",
            categories=[],
            evidence_urls=[url],
            confidence_score=0.9,
        )

    async def generate_digest(
        self, *, client_name: str, week_start: str, week_end: str, signals: list[tuple[str, str]]
    ) -> LlmDigestResult:
        return LlmDigestResult(subject="x", preheader="y", sections=[("z", ["a"])])


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
    headers = {"X-API-Key": "test-api-key"}

    r1 = rate_limited_client.post("/score-investors", headers=headers, json=payload)
    r2 = rate_limited_client.post("/score-investors", headers=headers, json=payload)
    r3 = rate_limited_client.post("/score-investors", headers=headers, json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
