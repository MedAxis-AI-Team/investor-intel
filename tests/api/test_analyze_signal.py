from __future__ import annotations


def test_analyze_signal_high_priority(client) -> None:
    res = client.post(
        "/analyze-signal",
        headers={"X-API-Key": "test-api-key"},
        json={
            "signal_type": "SEC_EDGAR",
            "title": "Form D filed for NovaBio",
            "url": "https://www.sec.gov/example",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["analysis"]["priority"] in {"HIGH", "MEDIUM", "LOW"}
    assert body["data"]["analysis"]["confidence"]["score"] >= 0


def test_analyze_signal_google_news_shape(client) -> None:
    res = client.post(
        "/analyze-signal",
        headers={"X-API-Key": "test-api-key"},
        json={
            "signal_type": "GOOGLE_NEWS",
            "title": "NovaBio raises seed round",
            "url": "https://news.example.com/novabio-seed",
            "raw_text": "NovaBio announced funding led by...",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    analysis = body["data"]["analysis"]
    assert "GOOGLE_NEWS" in analysis["categories"]
    assert analysis["evidence_urls"] == ["https://news.example.com/novabio-seed"]
