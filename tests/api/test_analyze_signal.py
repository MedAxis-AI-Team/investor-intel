from __future__ import annotations


def test_analyze_signal_high_priority(client) -> None:
    res = client.post(
        "/analyze-signal",
        json={
            "signal_type": "SEC_EDGAR",
            "title": "Form D filed for NovaBio",
            "url": "https://www.sec.gov/example",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    analysis = body["data"]["analysis"]
    assert analysis["priority"] in {"HIGH", "MEDIUM", "LOW"}
    assert analysis["confidence"]["score"] >= 0
    # New fields
    assert "relevance_score" in analysis
    assert "signal_type" in analysis
    assert "expires_relevance" in analysis
    assert "briefing" in analysis
    briefing = analysis["briefing"]
    assert briefing["headline"]
    assert briefing["why_it_matters"]
    assert briefing["outreach_angle"]
    assert briefing["suggested_contact"]
    assert briefing["time_sensitivity"]


def test_analyze_signal_google_news_shape(client) -> None:
    res = client.post(
        "/analyze-signal",
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


def test_analyze_signal_with_investor_context(client) -> None:
    res = client.post(
        "/analyze-signal",
        json={
            "signal_type": "SEC_EDGAR",
            "title": "Form D filed for NovaBio",
            "url": "https://www.sec.gov/example",
            "investor": {
                "name": "Flagship Pioneering",
                "thesis_keywords": ["biotech", "platform"],
                "portfolio_companies": ["Moderna"],
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_analyze_signal_with_client_context(client) -> None:
    res = client.post(
        "/analyze-signal",
        json={
            "signal_type": "GOOGLE_NEWS",
            "title": "Oncology breakthrough",
            "url": "https://news.example.com/oncology",
            "client": {
                "name": "NovaBio",
                "thesis": "Novel cancer diagnostics",
                "geography": "US",
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["success"] is True
