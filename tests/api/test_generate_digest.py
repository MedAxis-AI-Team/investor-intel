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
    assert body["data"]["payload"]["subject"]
    assert body["data"]["payload"]["preheader"]
    assert len(body["data"]["payload"]["sections"]) >= 1
    assert all("title" in s and "bullets" in s for s in body["data"]["payload"]["sections"])
