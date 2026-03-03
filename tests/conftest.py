from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import LlmDigestResult, LlmInvestorScore, LlmSignalAnalysis


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")

    # Ensure FastAPI settings cache is not polluted across tests
    os.environ.pop("REQUEST_TIMEOUT_SECONDS", None)
    os.environ.pop("RATE_LIMIT_WINDOW_SECONDS", None)
    os.environ.pop("RATE_LIMIT_MAX_REQUESTS", None)

    get_settings.cache_clear()


class _FakeLlmClient:
    async def score_investor(self, *, client_name: str, client_thesis: str, investor_name: str) -> LlmInvestorScore:
        evidence = [f"https://example.com/{investor_name.replace(' ', '-').lower()}"]
        return LlmInvestorScore(
            thesis_alignment=80,
            stage_fit=70,
            check_size_fit=60,
            strategic_value=50,
            notes=f"Scored {investor_name} for {client_name}.",
            evidence_urls=evidence,
            confidence_score=0.9,
        )

    async def analyze_signal(self, *, signal_type: str, title: str, url: str, raw_text: str | None) -> LlmSignalAnalysis:
        return LlmSignalAnalysis(
            priority="HIGH",
            rationale=f"High priority: {title}",
            categories=[signal_type],
            evidence_urls=[url],
            confidence_score=0.85,
        )

    async def generate_digest(
        self, *, client_name: str, week_start: str, week_end: str, signals: list[tuple[str, str]]
    ) -> LlmDigestResult:
        return LlmDigestResult(
            subject=f"Weekly Digest — {client_name}",
            preheader=f"Highlights for {week_start}–{week_end}",
            sections=[
                ("Market Pulse", ["Markets were active.", "Notable deals occurred."]),
                ("Signals", [f"{t} ({u})" for (t, u) in signals[:5]]),
            ],
        )


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _FakeLlmClient()
    return TestClient(app)
