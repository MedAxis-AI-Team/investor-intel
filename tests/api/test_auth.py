from __future__ import annotations


def test_auth_required_on_score_investors(client) -> None:
    res = client.post(
        "/score-investors",
        json={"client": {"name": "Acme", "thesis": "Biotech tools"}, "investors": [{"name": "Firm A"}]},
    )
    assert res.status_code == 401
    body = res.json()
    assert body["success"] is False
    assert body["error"]["message"] == "unauthorized"


def test_auth_accepts_valid_key(client) -> None:
    res = client.post(
        "/score-investors",
        headers={"X-API-Key": "test-api-key"},
        json={"client": {"name": "Acme", "thesis": "Biotech tools"}, "investors": [{"name": "Firm A"}]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
