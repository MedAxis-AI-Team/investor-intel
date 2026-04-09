"""Bulletproof validation tests — ensure bad payloads are rejected across all endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_validation_error(resp):
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


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
# POST /analyze-signal — validation failures (422)
# ===========================================================================


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
# POST /generate-digest — validation failures (422)
# ===========================================================================


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
# POST /score-grants — validation failures (422)
# ===========================================================================


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
