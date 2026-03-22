from __future__ import annotations

import pytest


def test_benchmark_returns_results(client) -> None:
    resp = client.post("/benchmark", json={
        "sample_size": 2,
        "skip_url_check": True,
        "skip_consistency": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total_cases"] == 2
    assert data["run_id"].startswith("run_")
    assert data["validation_pass_rate"] >= 0.0
    assert isinstance(data["case_results"], list)
    assert len(data["case_results"]) == 2


def test_benchmark_case_result_shape(client) -> None:
    resp = client.post("/benchmark", json={
        "sample_size": 1,
        "skip_url_check": True,
        "skip_consistency": True,
    })
    assert resp.status_code == 200
    case = resp.json()["data"]["case_results"][0]
    assert "test_case_id" in case
    assert "predicted_tier" in case
    assert "expected_tier" in case
    assert "score_snapshot" in case
    assert isinstance(case["critical_failures"], int)
    assert isinstance(case["warnings"], int)
    assert isinstance(case["passed"], int)


def test_benchmark_includes_confusion_matrix(client) -> None:
    resp = client.post("/benchmark", json={
        "skip_url_check": True,
        "skip_consistency": True,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["confusion"] is not None
    assert "matrix" in data["confusion"]
    assert "labels" in data["confusion"]
    assert "precision_weighted" in data["confusion"]


def test_benchmark_includes_hit_rate(client) -> None:
    resp = client.post("/benchmark", json={
        "skip_url_check": True,
        "skip_consistency": True,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["hit_rate"] is not None
    assert 0.0 <= data["hit_rate"] <= 1.0


def test_benchmark_default_skips(client) -> None:
    resp = client.post("/benchmark", json={})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_cases"] == 10
