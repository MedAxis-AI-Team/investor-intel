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


def test_analyze_signal_x_grok_returns_x_signal_type(client) -> None:
    """Test 9: x_grok source returns x_signal_type."""
    res = client.post(
        "/analyze-signal",
        json={
            "signal_type": "X_GROK",
            "title": "Excited about our Series B close",
            "url": "https://x.com/investor/status/123",
            "raw_text": "Just closed our Series B! $50M for precision oncology.",
            "client": {
                "name": "NovaBio",
                "thesis": "Precision oncology diagnostics",
                "modality": "diagnostics",
                "keywords": ["oncology", "precision medicine", "Series B"],
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    analysis = body["data"]["analysis"]
    assert analysis["x_signal_type"] is not None
    assert analysis["x_signal_type"] in {
        "thesis_statement", "conference_signal", "fund_activity",
        "portfolio_mention", "hiring_signal", "general_activity",
    }


def test_analyze_signal_non_x_grok_omits_x_signal_type(client) -> None:
    """Test 10: Non-x_grok source omits x_signal_type without failing validation."""
    res = client.post(
        "/analyze-signal",
        json={
            "signal_type": "GOOGLE_NEWS",
            "title": "NovaBio partnership announced",
            "url": "https://news.example.com/novabio-partnership",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    analysis = body["data"]["analysis"]
    assert analysis.get("x_signal_type") is None


def test_analyze_signal_x_grok_different_verticals(client) -> None:
    """Test 11: Two different client verticals produce valid responses for same post."""
    base_signal = {
        "signal_type": "X_GROK",
        "title": "Big news in healthcare AI",
        "url": "https://x.com/investor/status/456",
        "raw_text": "Healthcare AI is transforming diagnostics and drug discovery.",
    }

    res_diagnostics = client.post(
        "/analyze-signal",
        json={
            **base_signal,
            "client": {
                "name": "DiagCo",
                "thesis": "AI-powered diagnostics",
                "modality": "diagnostics",
                "keywords": ["AI", "diagnostics"],
            },
        },
    )
    assert res_diagnostics.status_code == 200
    assert res_diagnostics.json()["success"] is True
    assert res_diagnostics.json()["data"]["analysis"]["x_signal_type"] is not None

    res_pharma = client.post(
        "/analyze-signal",
        json={
            **base_signal,
            "client": {
                "name": "DrugCo",
                "thesis": "AI drug discovery platform",
                "modality": "therapeutics",
                "keywords": ["AI", "drug discovery"],
            },
        },
    )
    assert res_pharma.status_code == 200
    assert res_pharma.json()["success"] is True
    assert res_pharma.json()["data"]["analysis"]["x_signal_type"] is not None
