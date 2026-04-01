from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.main_deps import get_db_pool


# ── Fake DB helpers ────────────────────────────────────────────────────────────

_INVESTOR_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CLIENT_INVESTOR_UUID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_fake_conn(
    *,
    cross_ref_row=None,
    domain_row=None,
    client_investor_row=None,
    contact_existing=None,
    interaction_result="INSERT 0 1",
    gap_rows=None,
):
    """Build a mock asyncpg connection with configurable return values.

    fetchrow call order depends on cross-ref result:
    - Name match found:  [name_row, client_investor_row, contact_dedup]
    - Name miss, domain: [None, domain_row, client_investor_row, contact_dedup]
    - Both miss:         [None, None, client_investor_row, contact_dedup]
    """
    conn = AsyncMock()

    if cross_ref_row is not None:
        # Name matched — domain lookup is skipped
        fetchrow_side_effects = [
            cross_ref_row,
            client_investor_row or {"id": _CLIENT_INVESTOR_UUID},
            contact_existing,
        ]
    else:
        # Name miss → domain lookup is attempted
        fetchrow_side_effects = [
            None,
            domain_row,
            client_investor_row or {"id": _CLIENT_INVESTOR_UUID},
            contact_existing,
        ]

    conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effects)
    conn.execute = AsyncMock(return_value=interaction_result)

    if gap_rows is not None:
        conn.fetch = AsyncMock(return_value=gap_rows)

    return conn


def _make_fake_pool(conn):
    """Wrap a mock connection in a mock pool that supports async context manager."""
    pool = MagicMock()
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


def _transaction_conn(conn):
    """Patch conn.transaction() to return a working async context manager."""
    tx_ctx = AsyncMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=None)
    tx_ctx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_ctx)
    return conn


def _client_with_pool(pool):
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: pool
    return TestClient(app)


# ── Fixtures ───────────────────────────────────────────────────────────────────

_BUNDLE_PAYLOAD = {
    "client_id": "test-client",
    "investor": {
        "investor_name": "OrbiMed Advisors",
        "normalized_name": "orbimed advisors",
        "normalized_domain": "orbimed.com",
        "investor_type": "vc",
        "status": "active",
    },
    "contacts": [
        {"name": "Jane Doe", "email": "jane@orbimed.com", "title": "Partner"}
    ],
    "interactions": [
        {
            "event_date": "2026-03-01",
            "event_type": "outreach",
            "summary": "Good first call",
            "outcome": "interested",
            "raw_segment": "Called and discussed CAR-T",
        }
    ],
}


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_ingest_bundle_success():
    """Valid payload → 200, all 3 tables upserted, response structure correct."""
    conn = _transaction_conn(
        _make_fake_conn(
            cross_ref_row={"id": _INVESTOR_UUID},
            client_investor_row={"id": _CLIENT_INVESTOR_UUID},
            contact_existing=None,
            interaction_result="INSERT 0 1",
        )
    )
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["needs_enrichment"] is False
    assert data["contacts_upserted"] == 1
    assert data["interactions_upserted"] == 1
    assert data["investor_id"] is not None


def test_ingest_bundle_no_db():
    """Missing DATABASE_URL → 503 database_unavailable."""
    app = create_app()
    # No override — pool absent from app.state
    client = TestClient(app)

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "http_error"


def test_ingest_bundle_invalid_investor_type():
    """Bad investor_type enum → 422."""
    payload = {**_BUNDLE_PAYLOAD, "investor": {**_BUNDLE_PAYLOAD["investor"], "investor_type": "hedge_fund"}}
    conn = _transaction_conn(_make_fake_conn(cross_ref_row={"id": _INVESTOR_UUID}))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=payload)

    assert resp.status_code == 422


def test_ingest_bundle_invalid_event_type():
    """Bad event_type in interaction → 422."""
    payload = {
        **_BUNDLE_PAYLOAD,
        "interactions": [{"event_date": "2026-03-01", "event_type": "intro_call", "summary": "x"}],
    }
    conn = _transaction_conn(_make_fake_conn(cross_ref_row={"id": _INVESTOR_UUID}))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=payload)

    assert resp.status_code == 422


def test_ingest_bundle_empty_contacts():
    """Empty contacts list is accepted."""
    payload = {**_BUNDLE_PAYLOAD, "contacts": []}
    conn = _transaction_conn(
        _make_fake_conn(
            cross_ref_row={"id": _INVESTOR_UUID},
            client_investor_row={"id": _CLIENT_INVESTOR_UUID},
            interaction_result="INSERT 0 1",
        )
    )
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=payload)

    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_upserted"] == 0


def test_ingest_bundle_cross_ref_match():
    """When investor is found in core table → needs_enrichment=false, investor_id returned."""
    conn = _transaction_conn(
        _make_fake_conn(
            cross_ref_row={"id": _INVESTOR_UUID},
            client_investor_row={"id": _CLIENT_INVESTOR_UUID},
        )
    )
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    data = resp.json()["data"]
    assert data["needs_enrichment"] is False
    assert data["investor_id"] == str(_INVESTOR_UUID)


def test_ingest_bundle_cross_ref_no_match():
    """No match in core investors → needs_enrichment=true, investor_id=null."""
    # Both name and domain lookups return None
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=[
        None,  # name lookup miss
        None,  # domain lookup miss
        {"id": _CLIENT_INVESTOR_UUID},  # client_investor upsert
        None,  # contact dedup check
    ])
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    _transaction_conn(conn)
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["needs_enrichment"] is True
    assert data["investor_id"] is None


def test_ingest_bundle_duplicate_interaction_not_counted():
    """ON CONFLICT DO NOTHING → INSERT 0 0 → interactions_upserted=0."""
    conn = _transaction_conn(
        _make_fake_conn(
            cross_ref_row={"id": _INVESTOR_UUID},
            client_investor_row={"id": _CLIENT_INVESTOR_UUID},
            interaction_result="INSERT 0 0",
        )
    )
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 200
    assert resp.json()["data"]["interactions_upserted"] == 0


def test_gap_investors_returns_list():
    """Valid client_id → 200, gap_investors list returned."""
    gap_rows = [
        {"name": "a16z", "normalized_name": "a16z", "overall_score": 95, "investor_type": "vc"},
        {"name": "Sequoia", "normalized_name": "sequoia capital", "overall_score": 90, "investor_type": "vc"},
    ]
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=gap_rows)
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.get("/ingest/investor-gap/test-client")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["total"] == 2
    assert body["data"]["client_id"] == "test-client"
    assert len(body["data"]["gap_investors"]) == 2


def test_gap_investors_no_db():
    """No DATABASE_URL → 503."""
    app = create_app()
    client = TestClient(app)

    resp = client.get("/ingest/investor-gap/test-client")

    assert resp.status_code == 503


def test_gap_investors_limit_param():
    """limit query param is forwarded to the DB query."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.get("/ingest/investor-gap/test-client?limit=5")

    assert resp.status_code == 200
    # Verify the limit value was passed as second arg to fetch
    call_args = conn.fetch.call_args
    assert call_args.args[2] == 5
