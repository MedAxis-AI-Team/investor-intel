from __future__ import annotations


def test_generate_digest_returns_structured_payload_only(client) -> None:
    res = client.post(
        "/generate-digest",
        json={
            "client": {"name": "NovaBio", "geography": "US"},
            "week_start": "2026-03-01",
            "week_end": "2026-03-07",
            "signals": [{"title": "Grant awarded", "url": "https://example.com/grant"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["client_digest"]["subject"]
    assert body["data"]["client_digest"]["preheader"]
    assert len(body["data"]["client_digest"]["sections"]) >= 1
    assert all("title" in s and "bullets" in s for s in body["data"]["client_digest"]["sections"])


def test_generate_digest_x_activity_section(client) -> None:
    """Test 13: x_activity_section present; zero-signal returns empty array with section_note."""
    # Zero X signals — section still present with empty signals and section_note
    res_empty = client.post(
        "/generate-digest",
        json={
            "client": {"name": "NovaBio", "geography": "US"},
            "week_start": "2026-03-22",
            "week_end": "2026-03-28",
            "signals": [{"title": "FDA update", "url": "https://example.com/fda"}],
        },
    )
    assert res_empty.status_code == 200
    body_empty = res_empty.json()
    assert body_empty["success"] is True
    x_section = body_empty["data"]["client_digest"]["x_activity_section"]
    assert x_section is not None
    assert x_section["signals"] == []
    assert x_section["section_note"] is not None
    assert isinstance(x_section["section_note"], str)

    # With X signals — section populated with no null fields
    res_with = client.post(
        "/generate-digest",
        json={
            "client": {"name": "NovaBio", "geography": "US"},
            "week_start": "2026-03-22",
            "week_end": "2026-03-28",
            "signals": [{"title": "FDA update", "url": "https://example.com/fda"}],
            "x_signals": [
                {
                    "investor_name": "Jane Smith",
                    "firm": "Flagship Pioneering",
                    "signal_summary": "Posted about new fund close for oncology.",
                    "x_signal_type": "fund_activity",
                },
                {
                    "investor_name": "John Doe",
                    "firm": "ARCH Venture",
                    "signal_summary": "Mentioned attending JPM Healthcare Conference.",
                    "x_signal_type": "conference_signal",
                },
            ],
        },
    )
    assert res_with.status_code == 200
    body_with = res_with.json()
    assert body_with["success"] is True
    x_section_with = body_with["data"]["client_digest"]["x_activity_section"]
    assert len(x_section_with["signals"]) == 2
    for sig in x_section_with["signals"]:
        assert sig["investor_name"] is not None
        assert sig["firm"] is not None
        assert sig["signal_summary"] is not None
        assert sig["x_signal_type"] in {
            "thesis_statement", "conference_signal", "fund_activity",
            "portfolio_mention", "hiring_signal", "general_activity",
        }
        assert sig["recommended_action"] is not None
        assert sig["window"] in {"immediate", "this_week", "monitor"}
        assert sig["priority"] in {"high", "medium", "low"}
