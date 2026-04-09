from __future__ import annotations

from fastapi.testclient import TestClient


NOVABIO_PAYLOAD = {
    "schema_version": "2026-04-14",
    "client": {
        "name": "NovaBio Diagnostics",
        "thesis": (
            "AI-powered point-of-care diagnostics for wound infection detection. "
            "Stage: Series A. Funding target: $8M-12M. "
            "FDA pathway: 510(k) Class II with AI/ML software component. "
            "Keywords: wound care, point-of-care diagnostics, AI medical device."
        ),
        "geography": "US-based, open to EU investors",
        "funding_target": "$8M-12M",
        "competitor_watchlist": ["MolecuLight", "Tissue Analytics"],
    },
    "investors": [
        {
            "name": "OrbiMed Advisors",
            "website": "orbimed.com",
            "notes": (
                "Fund: $1.1B (Fund VIII). Recent deals: CompanyA $15M Series A 2025. "
                "Thesis: medtech, digital health, AI diagnostics. Partners: Jonathan Wang. "
                "Last activity: 2026-01-15. EDGAR: Form D filed 2026-02-18."
            ),
            "pipeline_status": "uncontacted",
        }
    ],
}


def test_smoke_score_investors_novabio(client: TestClient) -> None:
    resp = client.post("/score-investors", json=NOVABIO_PAYLOAD)
    assert resp.status_code == 200

    body = resp.json()
    assert body["success"] is True
    assert body["request_id"] is not None

    results = body["data"]["results"]
    advisor_data = body["data"]["advisor_data"]
    assert len(results) == 1

    result = results[0]
    assert result["investor"]["name"] == "OrbiMed Advisors"
    assert result["investor"]["pipeline_status"] == "uncontacted"
    assert isinstance(result["composite_score"], int)
    assert 0 <= result["composite_score"] <= 100

    # investor_tier and investor_source
    assert result["investor_tier"] in ("Tier 1", "Tier 2", "Below Threshold")
    assert result["investor_source"] in ("discovery", "client_provided")

    # narrative_summary and top_claims (client-facing)
    assert result["narrative_summary"]
    assert isinstance(result["top_claims"], list)

    # suggested_contact stays in client-facing result
    assert "suggested_contact" in result
    assert result["suggested_contact"]

    # Confidence
    assert result["confidence"]["tier"] in ("HIGH", "MEDIUM", "LOW")
    assert 0.0 <= result["confidence"]["score"] <= 1.0

    # dimension_strengths (client-facing, bucketed labels)
    ds = result["dimension_strengths"]
    for dim in ("strategic_fit", "stage_relevance", "capital_alignment", "market_activity", "geographic_proximity"):
        assert ds[dim] in ("High", "Medium", "Low"), f"dimension {dim} invalid: {ds[dim]}"

    # outreach_angle moved to advisor_data (internal)
    assert advisor_data[0]["outreach_angle"]

    # 6-axis breakdown in advisor_data (raw 0–100 scores)
    breakdown = advisor_data[0]["full_axis_breakdown"]
    for axis in ("thesis_alignment", "stage_fit", "check_size_fit", "recency", "geography"):
        assert axis in breakdown, f"Missing axis: {axis}"
        assert 0 <= breakdown[axis] <= 100
    assert "scientific_regulatory_fit" in breakdown

    # strategic_value must NOT be in the breakdown
    assert "strategic_value" not in breakdown


def test_smoke_score_investors_novabio_full_client_fields(client: TestClient) -> None:
    resp = client.post("/score-investors", json=NOVABIO_PAYLOAD)
    assert resp.status_code == 200

    body = resp.json()
    assert body["success"] is True
    # Validates schema_version in response matches the bumped version
    assert body["data"]["schema_version"] == "2026-04-14"


def test_smoke_analyze_signal_with_contexts(client: TestClient) -> None:
    payload = {
        "signal_type": "SEC_EDGAR",
        "title": "OrbiMed Fund VIII Form D Filing",
        "url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=orbimed",
        "published_at": "2026-02-18",
        "raw_text": "OrbiMed Advisors Fund VIII raised $1.1B targeting medtech and AI diagnostics.",
        "investor": {
            "name": "OrbiMed Advisors",
            "thesis_keywords": ["medtech", "digital health", "AI diagnostics"],
            "portfolio_companies": ["CompanyA"],
            "key_partners": ["Jonathan Wang"],
        },
        "client": {
            "name": "NovaBio Diagnostics",
            "thesis": "AI-powered point-of-care diagnostics for wound infection detection.",
            "geography": "US-based",
        },
    }
    resp = client.post("/analyze-signal", json=payload)
    assert resp.status_code == 200

    body = resp.json()
    assert body["success"] is True
    analysis = body["data"]["analysis"]
    assert analysis["priority"] in ("HIGH", "MEDIUM", "LOW")
    assert "briefing" in analysis
    assert "headline" in analysis["briefing"]


def test_smoke_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
