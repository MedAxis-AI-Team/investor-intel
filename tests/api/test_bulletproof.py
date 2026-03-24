"""Bulletproof variance tests — exercise edge cases across all endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_success(resp, *, status: int = 200):
    assert resp.status_code == status, f"Expected {status}, got {resp.status_code}: {resp.text}"
    body = resp.json()
    if status == 200:
        assert body["success"] is True
        assert body["request_id"] is not None
    return body


def _assert_validation_error(resp):
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ===========================================================================
# POST /score-investors — variances
# ===========================================================================


class TestScoreInvestorsVariances:
    """Payload variances for /score-investors."""

    # --- Minimal payload (only required fields) ---

    def test_minimal_payload(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "X", "thesis": "Biotech Series A"},
            "investors": [{"name": "Y"}],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        r = body["data"]["results"][0]
        assert r["investor"]["name"] == "Y"
        assert r["investor"]["website"] is None
        assert r["investor"]["notes"] is None
        assert r["investor"]["pipeline_status"] is None

    # --- All optional fields populated ---

    def test_full_payload(self, client: TestClient) -> None:
        payload = {
            "schema_version": "2026-03-03",
            "client": {
                "name": "NovaBio Diagnostics",
                "thesis": "AI-powered point-of-care diagnostics.",
                "geography": "US-based, open to EU investors",
                "funding_target": "$8M-12M",
                "competitor_watchlist": ["MolecuLight", "Tissue Analytics"],
            },
            "investors": [
                {
                    "name": "OrbiMed Advisors",
                    "website": "orbimed.com",
                    "notes": "Fund VIII, $1.1B, medtech focus.",
                    "pipeline_status": "uncontacted",
                },
            ],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        r = body["data"]["results"][0]
        assert r["investor"]["pipeline_status"] == "uncontacted"
        assert r["outreach_angle"]
        assert r["suggested_contact"]

    # --- Batch: multiple investors ---

    def test_batch_multiple_investors(self, client: TestClient) -> None:
        investors = [{"name": f"Investor {i}"} for i in range(5)]
        payload = {
            "client": {"name": "Client", "thesis": "Gene therapy for rare diseases."},
            "investors": investors,
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        assert len(body["data"]["results"]) == 5
        names = {r["investor"]["name"] for r in body["data"]["results"]}
        assert names == {f"Investor {i}" for i in range(5)}

    # --- Every pipeline_status value ---

    @pytest.mark.parametrize(
        "status",
        ["uncontacted", "outreach_sent", "meeting_scheduled", "active_dialogue", "passed", "committed"],
    )
    def test_all_pipeline_statuses(self, client: TestClient, status: str) -> None:
        payload = {
            "client": {"name": "C", "thesis": "Digital health SaaS."},
            "investors": [{"name": "V", "pipeline_status": status}],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        assert body["data"]["results"][0]["investor"]["pipeline_status"] == status

    # --- Null optional fields ---

    def test_null_optionals(self, client: TestClient) -> None:
        payload = {
            "client": {
                "name": "NullTest Co",
                "thesis": "Platform for clinical trials.",
                "geography": None,
                "funding_target": None,
                "competitor_watchlist": [],
            },
            "investors": [
                {"name": "Fund A", "website": None, "notes": None, "pipeline_status": None}
            ],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        r = body["data"]["results"][0]
        assert r["investor"]["website"] is None
        assert r["investor"]["notes"] is None

    # --- Max investor batch (50) ---

    def test_max_batch_size(self, client: TestClient) -> None:
        investors = [{"name": f"Inv-{i:03d}"} for i in range(50)]
        payload = {
            "client": {"name": "Batch Co", "thesis": "mRNA therapeutics platform."},
            "investors": investors,
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        assert len(body["data"]["results"]) == 50

    # --- 6-axis breakdown shape ---

    def test_breakdown_shape(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "Shape Co", "thesis": "Microfluidics for diagnostics."},
            "investors": [{"name": "VC Alpha"}],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        breakdown = body["data"]["results"][0]["breakdown"]
        expected_axes = {"thesis_alignment", "stage_fit", "check_size_fit",
                         "scientific_regulatory_fit", "recency", "geography"}
        assert set(breakdown.keys()) == expected_axes
        assert "strategic_value" not in breakdown

    # --- Long thesis text ---

    def test_long_thesis(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "Verbose Inc", "thesis": "x " * 1999},  # 3998 chars
            "investors": [{"name": "LP1"}],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        assert body["data"]["results"][0]["overall_score"] >= 0

    # --- Long investor notes ---

    def test_long_investor_notes(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "LongNotes Co", "thesis": "Digital biomarkers."},
            "investors": [{"name": "Fund Z", "notes": "data " * 399}],  # 1995 chars
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        assert body["data"]["results"][0]["confidence"]["tier"] in ("HIGH", "MEDIUM", "LOW")

    # --- Unicode and special characters ---

    def test_unicode_names(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "München BioTech GmbH", "thesis": "Krebsdiagnostik mit KI."},
            "investors": [{"name": "Zürich Ventures — α Fund"}],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        assert body["data"]["results"][0]["investor"]["name"] == "Zürich Ventures — α Fund"

    # --- Empty competitor watchlist ---

    def test_empty_watchlist(self, client: TestClient) -> None:
        payload = {
            "client": {
                "name": "WL Co",
                "thesis": "Companion diagnostics.",
                "competitor_watchlist": [],
            },
            "investors": [{"name": "Fund W"}],
        }
        body = _assert_success(client.post("/score-investors", json=payload))
        assert body["success"] is True

    # --- Max competitor watchlist (10) ---

    def test_full_watchlist(self, client: TestClient) -> None:
        payload = {
            "client": {
                "name": "WL Full Co",
                "thesis": "Oncology panel sequencing.",
                "competitor_watchlist": [f"Comp{i}" for i in range(10)],
            },
            "investors": [{"name": "Fund F"}],
        }
        _assert_success(client.post("/score-investors", json=payload))


# ===========================================================================
# POST /score-investors — validation failures (422)
# ===========================================================================


class TestScoreInvestorsValidation:
    """Ensure bad payloads are rejected, not 500."""

    def test_empty_body(self, client: TestClient) -> None:
        _assert_validation_error(client.post("/score-investors", json={}))

    def test_missing_client(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={"investors": [{"name": "X"}]})
        )

    def test_missing_investors(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={"client": {"name": "C", "thesis": "t"}})
        )

    def test_empty_investors_list(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={
                "client": {"name": "C", "thesis": "t"},
                "investors": [],
            })
        )

    def test_investor_name_empty(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={
                "client": {"name": "C", "thesis": "t"},
                "investors": [{"name": ""}],
            })
        )

    def test_client_name_empty(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={
                "client": {"name": "", "thesis": "t"},
                "investors": [{"name": "V"}],
            })
        )

    def test_client_thesis_empty(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={
                "client": {"name": "C", "thesis": ""},
                "investors": [{"name": "V"}],
            })
        )

    def test_invalid_pipeline_status(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={
                "client": {"name": "C", "thesis": "t"},
                "investors": [{"name": "V", "pipeline_status": "INVALID"}],
            })
        )

    def test_over_50_investors(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={
                "client": {"name": "C", "thesis": "t"},
                "investors": [{"name": f"V{i}"} for i in range(51)],
            })
        )

    def test_thesis_exceeds_max_length(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-investors", json={
                "client": {"name": "C", "thesis": "x" * 4001},
                "investors": [{"name": "V"}],
            })
        )


# ===========================================================================
# POST /analyze-signal — variances
# ===========================================================================


class TestAnalyzeSignalVariances:
    """Payload variances for /analyze-signal."""

    def test_minimal_payload(self, client: TestClient) -> None:
        payload = {
            "signal_type": "OTHER",
            "title": "Generic signal",
            "url": "https://example.com/signal",
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        assert body["data"]["analysis"]["priority"] in ("HIGH", "MEDIUM", "LOW")
        assert body["data"]["analysis"]["briefing"]["headline"]

    @pytest.mark.parametrize("sig_type", ["SEC_EDGAR", "GOOGLE_NEWS", "OTHER"])
    def test_all_signal_types(self, client: TestClient, sig_type: str) -> None:
        payload = {
            "signal_type": sig_type,
            "title": f"Test {sig_type}",
            "url": "https://example.com/test",
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        assert body["data"]["analysis"]["priority"] in ("HIGH", "MEDIUM", "LOW")

    def test_full_payload_with_both_contexts(self, client: TestClient) -> None:
        payload = {
            "signal_type": "SEC_EDGAR",
            "title": "Form D Filing",
            "url": "https://sec.gov/filing/123",
            "published_at": "2026-03-20",
            "raw_text": "Company raised $50M Series B for AI diagnostics platform.",
            "investor": {
                "name": "Flagship Pioneering",
                "current_score": 82,
                "thesis_keywords": ["biotech", "platform", "AI"],
                "portfolio_companies": ["Moderna", "Denali"],
                "key_partners": ["Noubar Afeyan"],
            },
            "client": {
                "name": "DiagCo",
                "thesis": "AI diagnostics for early cancer detection.",
                "geography": "US East Coast",
            },
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        analysis = body["data"]["analysis"]
        assert analysis["briefing"]["suggested_contact"]
        assert 0 <= analysis["relevance_score"] <= 100
        assert analysis["signal_type"]
        assert analysis["expires_relevance"]

    def test_investor_context_only(self, client: TestClient) -> None:
        payload = {
            "signal_type": "GOOGLE_NEWS",
            "title": "Flagship launches new fund",
            "url": "https://news.example.com/article",
            "investor": {"name": "Flagship Pioneering"},
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        assert body["data"]["analysis"]["priority"] in ("HIGH", "MEDIUM", "LOW")

    def test_client_context_only(self, client: TestClient) -> None:
        payload = {
            "signal_type": "OTHER",
            "title": "FDA clears new device pathway",
            "url": "https://fda.gov/clearance/456",
            "client": {"name": "DeviceCo", "thesis": "510(k) wound care devices."},
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        assert body["data"]["analysis"]["priority"] in ("HIGH", "MEDIUM", "LOW")

    def test_long_raw_text(self, client: TestClient) -> None:
        payload = {
            "signal_type": "OTHER",
            "title": "Long article",
            "url": "https://example.com/long",
            "raw_text": "Lorem ipsum. " * 1500,  # ~19500 chars
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        assert body["success"] is True

    def test_investor_with_empty_lists(self, client: TestClient) -> None:
        payload = {
            "signal_type": "SEC_EDGAR",
            "title": "Filing",
            "url": "https://sec.gov/test",
            "investor": {
                "name": "Empty Lists Fund",
                "thesis_keywords": [],
                "portfolio_companies": [],
                "key_partners": [],
            },
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        assert body["success"] is True

    def test_unicode_signal(self, client: TestClient) -> None:
        payload = {
            "signal_type": "GOOGLE_NEWS",
            "title": "Société Générale lance un fonds biotech — €200M",
            "url": "https://example.fr/article",
            "raw_text": "Investissement dans les diagnostics médicaux avancés.",
        }
        body = _assert_success(client.post("/analyze-signal", json=payload))
        assert body["success"] is True


class TestAnalyzeSignalValidation:
    """Ensure bad payloads are rejected."""

    def test_empty_body(self, client: TestClient) -> None:
        _assert_validation_error(client.post("/analyze-signal", json={}))

    def test_missing_title(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/analyze-signal", json={"signal_type": "OTHER", "url": "https://x.com"})
        )

    def test_missing_url(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/analyze-signal", json={"signal_type": "OTHER", "title": "T"})
        )

    def test_invalid_signal_type(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/analyze-signal", json={
                "signal_type": "TWITTER",
                "title": "Tweet",
                "url": "https://x.com/status/1",
            })
        )

    def test_investor_context_missing_name(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/analyze-signal", json={
                "signal_type": "OTHER",
                "title": "T",
                "url": "https://x.com",
                "investor": {"thesis_keywords": ["bio"]},
            })
        )

    def test_client_context_missing_thesis(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/analyze-signal", json={
                "signal_type": "OTHER",
                "title": "T",
                "url": "https://x.com",
                "client": {"name": "Co"},
            })
        )


# ===========================================================================
# POST /generate-digest — variances
# ===========================================================================


class TestGenerateDigestVariances:
    """Payload variances for /generate-digest."""

    def test_minimal_payload(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "DigestCo"},
            "week_start": "2026-03-17",
            "week_end": "2026-03-23",
        }
        body = _assert_success(client.post("/generate-digest", json=payload))
        p = body["data"]["payload"]
        assert p["subject"]
        assert p["preheader"]
        assert len(p["sections"]) >= 1

    def test_full_payload(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "NovaBio", "geography": "US"},
            "week_start": "2026-03-17",
            "week_end": "2026-03-23",
            "signals": [
                {"title": "OrbiMed Fund VIII Filing", "url": "https://sec.gov/filing/1"},
                {"title": "New FDA guidance", "url": "https://fda.gov/news", "summary": "Updated 510(k)."},
            ],
            "investors": [
                {"name": "OrbiMed", "pipeline_status": "uncontacted"},
                {"name": "ARCH Venture", "pipeline_status": "meeting_scheduled"},
            ],
            "market_context": "Biotech index up 3% this week. Notable IPO activity.",
        }
        body = _assert_success(client.post("/generate-digest", json=payload))
        assert len(body["data"]["payload"]["sections"]) >= 1

    def test_empty_signals_and_investors(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "EmptyCo"},
            "week_start": "2026-03-17",
            "week_end": "2026-03-23",
            "signals": [],
            "investors": [],
        }
        body = _assert_success(client.post("/generate-digest", json=payload))
        assert body["success"] is True

    def test_many_signals(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "BulkCo"},
            "week_start": "2026-03-17",
            "week_end": "2026-03-23",
            "signals": [
                {"title": f"Signal {i}", "url": f"https://example.com/s/{i}"}
                for i in range(20)
            ],
        }
        body = _assert_success(client.post("/generate-digest", json=payload))
        assert body["success"] is True

    def test_null_market_context(self, client: TestClient) -> None:
        payload = {
            "client": {"name": "NullMktCo"},
            "week_start": "2026-03-17",
            "week_end": "2026-03-23",
            "market_context": None,
        }
        body = _assert_success(client.post("/generate-digest", json=payload))
        assert body["success"] is True


class TestGenerateDigestValidation:

    def test_empty_body(self, client: TestClient) -> None:
        _assert_validation_error(client.post("/generate-digest", json={}))

    def test_missing_client(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/generate-digest", json={
                "week_start": "2026-03-17", "week_end": "2026-03-23",
            })
        )

    def test_missing_week_start(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/generate-digest", json={
                "client": {"name": "C"}, "week_end": "2026-03-23",
            })
        )

    def test_missing_week_end(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/generate-digest", json={
                "client": {"name": "C"}, "week_start": "2026-03-17",
            })
        )


# ===========================================================================
# POST /score-grants — variances
# ===========================================================================


class TestScoreGrantsVariances:
    """Payload variances for /score-grants."""

    def test_minimal_payload(self, client: TestClient) -> None:
        payload = {
            "client_profile": {
                "company_name": "GrantCo",
                "therapeutic_area": "Oncology",
                "stage": "Preclinical",
            },
            "grants": [
                {
                    "source": "grants.gov",
                    "title": "SBIR Phase I: Cancer Diagnostics",
                    "agency": "NIH",
                    "url": "https://grants.gov/grant/1",
                },
            ],
        }
        body = _assert_success(client.post("/score-grants", json=payload))
        g = body["data"]["scored_grants"][0]
        assert g["title"] == "SBIR Phase I: Cancer Diagnostics"
        assert 0 <= g["overall_score"] <= 100
        assert g["confidence"] in ("high", "medium", "low")
        assert g["rationale"]

    def test_full_payload(self, client: TestClient) -> None:
        payload = {
            "client_profile": {
                "company_name": "NovaBio Diagnostics",
                "therapeutic_area": "Wound care diagnostics",
                "stage": "Series A",
                "fda_pathway": "510(k) Class II",
                "keywords": ["AI", "wound care", "point-of-care", "diagnostics"],
            },
            "grants": [
                {
                    "source": "grants.gov",
                    "title": "BARDA DRIVe: Rapid Infection Diagnostics",
                    "agency": "HHS/BARDA",
                    "program": "DRIVe",
                    "award_amount": "$2M-$5M",
                    "deadline": "2026-06-30",
                    "description": "Seeking POC diagnostics for rapid bacterial identification.",
                    "eligibility": "US-based small businesses with FDA-ready prototypes.",
                    "url": "https://grants.gov/grant/BARDA-2026-01",
                },
            ],
        }
        body = _assert_success(client.post("/score-grants", json=payload))
        g = body["data"]["scored_grants"][0]
        assert g["agency"] == "HHS/BARDA"
        assert g["program"] == "DRIVe"
        assert g["breakdown"]["therapeutic_match"] >= 0
        assert g["breakdown"]["stage_eligibility"] >= 0
        assert g["breakdown"]["award_size_relevance"] >= 0
        assert g["breakdown"]["deadline_feasibility"] >= 0
        assert g["breakdown"]["historical_funding"] >= 0

    def test_multiple_grants(self, client: TestClient) -> None:
        grants = [
            {
                "source": f"source-{i}",
                "title": f"Grant {i}",
                "agency": "NIH",
                "url": f"https://grants.gov/grant/{i}",
            }
            for i in range(5)
        ]
        payload = {
            "client_profile": {
                "company_name": "MultiGrant Co",
                "therapeutic_area": "Immunology",
                "stage": "Phase I",
            },
            "grants": grants,
        }
        body = _assert_success(client.post("/score-grants", json=payload))
        assert len(body["data"]["scored_grants"]) == 5
        assert body["data"]["summary"]

    def test_null_optional_fields(self, client: TestClient) -> None:
        payload = {
            "client_profile": {
                "company_name": "NullGrant Co",
                "therapeutic_area": "Neurology",
                "stage": "Discovery",
                "fda_pathway": None,
                "keywords": [],
            },
            "grants": [
                {
                    "source": "grants.gov",
                    "title": "Brain Initiative Grant",
                    "agency": "NIH/NINDS",
                    "program": None,
                    "award_amount": None,
                    "deadline": None,
                    "description": None,
                    "eligibility": None,
                    "url": "https://grants.gov/grant/brain-1",
                },
            ],
        }
        body = _assert_success(client.post("/score-grants", json=payload))
        assert body["data"]["scored_grants"][0]["confidence"] in ("high", "medium", "low")

    def test_unicode_grant(self, client: TestClient) -> None:
        payload = {
            "client_profile": {
                "company_name": "Société BioTech",
                "therapeutic_area": "Thérapie génique",
                "stage": "Préclinique",
            },
            "grants": [
                {
                    "source": "horizon-europe",
                    "title": "Programme Européen — Diagnostics Avancés",
                    "agency": "European Commission",
                    "url": "https://ec.europa.eu/grant/1",
                },
            ],
        }
        body = _assert_success(client.post("/score-grants", json=payload))
        assert body["data"]["scored_grants"][0]["title"] == "Programme Européen — Diagnostics Avancés"


class TestScoreGrantsValidation:

    def test_empty_body(self, client: TestClient) -> None:
        _assert_validation_error(client.post("/score-grants", json={}))

    def test_missing_client_profile(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-grants", json={
                "grants": [{"source": "x", "title": "t", "agency": "a", "url": "https://x.com"}],
            })
        )

    def test_missing_grants(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-grants", json={
                "client_profile": {
                    "company_name": "C", "therapeutic_area": "T", "stage": "S",
                },
            })
        )

    def test_empty_grants_list(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-grants", json={
                "client_profile": {
                    "company_name": "C", "therapeutic_area": "T", "stage": "S",
                },
                "grants": [],
            })
        )

    def test_grant_missing_required_fields(self, client: TestClient) -> None:
        _assert_validation_error(
            client.post("/score-grants", json={
                "client_profile": {
                    "company_name": "C", "therapeutic_area": "T", "stage": "S",
                },
                "grants": [{"source": "x"}],  # missing title, agency, url
            })
        )


# ===========================================================================
# GET /health — sanity
# ===========================================================================


class TestHealthVariances:

    def test_health_returns_ok(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["status"] == "ok"

    def test_health_ignores_query_params(self, client: TestClient) -> None:
        resp = client.get("/health?foo=bar&baz=1")
        assert resp.status_code == 200

    def test_health_post_not_allowed(self, client: TestClient) -> None:
        resp = client.post("/health")
        assert resp.status_code == 405
