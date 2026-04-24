from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.main_deps import get_llm_client
from app.services.llm_client import LlmInvestorScore, LlmRetryExhaustedError

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
    advisor_data = body["data"]["advisor_data"]
    assert results[0]["investor"]["name"] == "Firm A"
    assert results[1]["investor"]["name"] == "Firm B"
    assert results[0]["confidence"]["tier"] in {"HIGH", "MEDIUM", "LOW"}
    # New client-facing score fields
    assert isinstance(results[0]["composite_score"], int)
    assert results[0]["investor_tier"] in {"Tier 1", "Tier 2", "Below Threshold"}
    assert results[0]["investor_source"] in {"discovery", "client_provided"}
    assert results[0]["narrative_summary"]
    assert isinstance(results[0]["top_claims"], list)
    assert results[0]["suggested_contact"]
    # dimension_strengths present
    ds = results[0]["dimension_strengths"]
    assert ds["strategic_fit"] in {"High", "Medium", "Low"}
    assert ds["stage_relevance"] in {"High", "Medium", "Low"}
    # Advisor-internal data in advisor_data parallel list
    assert len(advisor_data) == 2
    assert advisor_data[0]["outreach_angle"]
    breakdown = advisor_data[0]["full_axis_breakdown"]
    assert "thesis_alignment" in breakdown
    assert "stage_fit" in breakdown
    assert "check_size_fit" in breakdown
    assert "recency" in breakdown
    assert "geography" in breakdown


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
                outreach_angle="Generic outreach.",
                avoid=None,
                suggested_contact="Partner",
                evidence_urls=[],
                confidence_score=0.8,
                narrative_summary="Summary.",
                top_claims=[],
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


def test_score_investors_null_sci_reg_for_b2b_client(client) -> None:
    """B2B thesis with no FDA terms must produce scientific_regulatory_fit=null."""
    res = client.post(
        "/score-investors",
        json={
            "client": {
                "name": "Nanofacile",
                "thesis": (
                    "B2B platform enabling nanomaterial synthesis for research labs. "
                    "Stage: Seed. No FDA pathway. Keywords: nanomaterials, lab automation, "
                    "B2B platform, enabling technology."
                ),
                "geography": "Montreal, Canada",
                "funding_target": "$2M-4M",
                "competitor_watchlist": [],
            },
            "investors": [{"name": "BDC Capital", "notes": "Canadian VC. Invests in deep tech.", "pipeline_status": "uncontacted"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    result = body["data"]["results"][0]
    advisor = body["data"]["advisor_data"][0]
    assert advisor["full_axis_breakdown"]["scientific_regulatory_fit"] is None
    assert result["composite_score"] > 0


def test_grant_type_skips_llm_and_returns_stub(client) -> None:
    """Grant-type investors must be excluded from VC scoring and return a zero-score stub."""
    res = client.post(
        "/score-investors",
        json={
            "client": {"name": "NovaBio", "thesis": "Diagnostics"},
            "investors": [
                {"name": "NIH Grant", "investor_type": "grant"},
                {"name": "Firm A"},
            ],
        },
    )
    assert res.status_code == 200
    body = res.json()
    results = body["data"]["results"]
    advisor_data = body["data"]["advisor_data"]

    grant_result = results[0]
    assert grant_result["composite_score"] == 0
    assert grant_result["investor_tier"] == "Below Threshold"
    assert grant_result["confidence"]["tier"] == "LOW"
    assert "grant" in grant_result["narrative_summary"].lower()

    grant_advisor = advisor_data[0]
    assert "[GRANT]" in grant_advisor["notes"]
    assert grant_advisor["outreach_angle"] == ""

    # Non-grant investor scores normally
    assert results[1]["composite_score"] > 0


def test_angel_type_caps_confidence_at_medium(client) -> None:
    """Angel-type investors must be scored but confidence capped at MEDIUM."""
    res = client.post(
        "/score-investors",
        json={
            "client": {"name": "NovaBio", "thesis": "Diagnostics"},
            "investors": [{"name": "Angel Investor", "investor_type": "angel"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    result = body["data"]["results"][0]
    advisor = body["data"]["advisor_data"][0]

    # Should score (not a stub) but confidence must not be HIGH
    assert result["composite_score"] > 0
    assert result["confidence"]["tier"] != "HIGH"

    # Angel flag must appear in advisor notes
    assert "[ANGEL]" in advisor["notes"]


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
            scoring_instructions=None,
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
                avoid=None,
                suggested_contact="Partner",
                evidence_urls=["https://example.com/ev"],
                confidence_score=0.9,
                narrative_summary="Summary.",
                top_claims=["Claim 1."],
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
    body = res.json()
    result = body["data"]["results"][0]
    advisor = body["data"]["advisor_data"][0]
    assert advisor["full_axis_breakdown"]["scientific_regulatory_fit"] is None
    assert result["composite_score"] > 0


def test_digital_health_profile_scores_sci_reg(client) -> None:
    """digital_health profile must produce non-null scientific_regulatory_fit (tech differentiation axis)."""
    res = client.post(
        "/score-investors",
        json={
            "client": {
                "name": "Predictive Healthcare",
                "thesis": (
                    "AI-enabled remote patient monitoring SaaS platform. "
                    "Targets chronic disease management for health systems."
                ),
                "client_profile": "digital_health",
                "modifiers": ["ai_enabled", "rpm_saas"],
            },
            "investors": [{"name": "General Catalyst"}, {"name": "7wireVentures"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    results = body["data"]["results"]
    advisor_data = body["data"]["advisor_data"]
    assert len(results) == 2
    # digital_health always scores scientific_regulatory_fit (tech differentiation)
    for advisor in advisor_data:
        assert advisor["full_axis_breakdown"]["scientific_regulatory_fit"] is not None
    # Sanity-check standard response structure
    assert results[0]["investor_tier"] in {"Tier 1", "Tier 2", "Below Threshold"}
    assert results[0]["composite_score"] > 0


def test_medical_device_profile_scores_sci_reg(client) -> None:
    """medical_device profile must produce non-null scientific_regulatory_fit (device pathway axis)."""
    res = client.post(
        "/score-investors",
        json={
            "client": {
                "name": "Crimson Scientific",
                "thesis": (
                    "Reusable wireless EKG device. FDA Class II, 510(k) exempt pathway. "
                    "Targeting hospital bedside monitoring."
                ),
                "client_profile": "medical_device",
                "modifiers": [],
            },
            "investors": [{"name": "Vensana Capital"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    advisor = body["data"]["advisor_data"][0]
    # medical_device always scores scientific_regulatory_fit (device pathway alignment)
    assert advisor["full_axis_breakdown"]["scientific_regulatory_fit"] is not None
    assert body["data"]["results"][0]["composite_score"] > 0


def test_therapeutic_default_preserves_existing_behavior(client) -> None:
    """No client_profile field must default to therapeutic and preserve existing behavior."""
    res = client.post(
        "/score-investors",
        json={
            "client": {
                "name": "NovaBio",
                "thesis": "B2B diagnostics platform. No FDA pathway.",
            },
            "investors": [{"name": "Firm A"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    # therapeutic + no FDA terms in thesis → scientific_regulatory_fit is null
    advisor = body["data"]["advisor_data"][0]
    assert advisor["full_axis_breakdown"]["scientific_regulatory_fit"] is None


def test_llm_retry_exhausted_returns_held_for_review(monkeypatch) -> None:
    """When the LLM can't return valid JSON after retries, return held_for_review."""
    class _BadJsonLlm:
        async def score_investor(self, **kwargs) -> LlmInvestorScore:  # type: ignore[override]
            raise LlmRetryExhaustedError(raw="not json at all { broken")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _BadJsonLlm()
    test_client = TestClient(app)

    res = test_client.post(
        "/score-investors",
        json={"client": {"name": "Acme", "thesis": "Bio"}, "investors": [{"name": "Firm A"}]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "held_for_review"


def test_score_investors_truncates_oversized_llm_fields(monkeypatch) -> None:
    """Production uses LLM_MAX_TOKENS=8192 which can return text exceeding model max_length constraints.
    The service must truncate before constructing response models or a pydantic.ValidationError
    escapes to the global Exception handler and returns HTTP 500."""

    class _OversizedLlmClient:
        async def score_investor(self, **kwargs) -> LlmInvestorScore:
            return LlmInvestorScore(
                thesis_alignment=80,
                stage_fit=70,
                check_size_fit=60,
                scientific_regulatory_fit=55,
                recency=65,
                geography=50,
                notes="N" * 3000,
                outreach_angle="O" * 3000,
                avoid="A" * 1500,
                suggested_contact="Partner",
                evidence_urls=[f"https://example.com/{i}" for i in range(30)],
                confidence_score=0.85,
                narrative_summary="S" * 3000,
                top_claims=["C"] * 10,
            )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: _OversizedLlmClient()
    test_client = TestClient(app)

    res = test_client.post(
        "/score-investors",
        json={
            "client": {"name": "Acme", "thesis": "Bio"},
            "investors": [{"name": "Firm A"}, {"name": "Firm B"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True

    results = body["data"]["results"]
    advisor_data = body["data"]["advisor_data"]
    assert len(results) == 2
    assert len(advisor_data) == 2

    assert len(results[0]["narrative_summary"]) <= 2000
    assert len(advisor_data[0]["outreach_angle"]) <= 2000
    assert advisor_data[0]["avoid"] is None or len(advisor_data[0]["avoid"]) <= 1000
    assert advisor_data[0]["notes"] is None or len(advisor_data[0]["notes"]) <= 2000
    assert len(advisor_data[0]["evidence_urls"]) <= 20
