from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.main_deps import get_db_pool


# ── Constants ─────────────────────────────────────────────────────────────────

_INVESTOR_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_CLIENT_INVESTOR_UUID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_CLIENT_UUID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


# ── Fake DB helpers ────────────────────────────────────────────────────────────

def _make_fake_conn(fetchrow_results: list, execute_result: str = "INSERT 0 1", fetch_result=None):
    """Build a mock asyncpg connection.

    fetchrow_results: ordered list of return values for each fetchrow call.
    execute_result:   return value for conn.execute calls.
    fetch_result:     return value for conn.fetch calls (gap query).
    """
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow_results)
    conn.execute = AsyncMock(return_value=execute_result)
    if fetch_result is not None:
        conn.fetch = AsyncMock(return_value=fetch_result)
    return conn


def _transaction_conn(conn):
    tx_ctx = AsyncMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=None)
    tx_ctx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_ctx)
    return conn


def _make_fake_pool(conn):
    pool = MagicMock()
    acquire_ctx = AsyncMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


def _client_with_pool(pool):
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: pool
    return TestClient(app)


# ── Fixtures ───────────────────────────────────────────────────────────────────

_BUNDLE_PAYLOAD = {
    "client_id": str(_CLIENT_UUID),
    "investor": {
        "firm_name": "OrbiMed Advisors",
        "investor_type": "vc",
        "relationship_status": "active",
    },
    "contacts": [
        {"full_name": "Jane Doe", "email": "jane@orbimed.com", "title": "Partner"}
    ],
    "interactions": [
        {
            "interaction_date": "2026-03-01",
            "interaction_type": "outreach",
            "summary": "Good first call",
            "outcome": "interested",
            "raw_note_excerpt": "Called and discussed CAR-T",
        }
    ],
}

# fetchrow call sequence for happy path (name match found, no existing client_investor):
# 1. _cross_ref_investor name lookup → found
# 2. _upsert_client_investor existing check → None (not found)
# 3. _upsert_client_investor INSERT RETURNING → client_investor_row
# 4. _upsert_contacts email check → None (not found)
_HAPPY_PATH_FETCHROWS = [
    {"id": _INVESTOR_UUID},        # cross_ref name match
    None,                           # client_investor existing check
    {"id": _CLIENT_INVESTOR_UUID}, # client_investor INSERT
    None,                           # contact email dedup
]


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_ingest_bundle_success():
    """Valid payload → 200, all 3 tables upserted, response structure correct."""
    conn = _transaction_conn(_make_fake_conn(_HAPPY_PATH_FETCHROWS))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["contacts_upserted"] == 1
    assert data["interactions_upserted"] == 1
    assert data["investor_id"] is not None
    assert data["client_investor_id"] is not None


def test_ingest_bundle_no_db():
    """Missing DATABASE_URL → 503 database_unavailable."""
    app = create_app()
    client = TestClient(app)

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "http_error"


def test_ingest_bundle_invalid_investor_type():
    """Bad investor_type enum → 422."""
    payload = {**_BUNDLE_PAYLOAD, "investor": {**_BUNDLE_PAYLOAD["investor"], "investor_type": "hedge_fund"}}
    conn = _transaction_conn(_make_fake_conn(_HAPPY_PATH_FETCHROWS))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=payload)

    assert resp.status_code == 422


def test_ingest_bundle_invalid_interaction_type():
    """Bad interaction_type → 422."""
    payload = {
        **_BUNDLE_PAYLOAD,
        "interactions": [{"interaction_date": "2026-03-01", "interaction_type": "intro_call", "summary": "x"}],
    }
    conn = _transaction_conn(_make_fake_conn(_HAPPY_PATH_FETCHROWS))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=payload)

    assert resp.status_code == 422


def test_ingest_bundle_empty_contacts():
    """Empty contacts list is accepted."""
    payload = {**_BUNDLE_PAYLOAD, "contacts": []}
    # No contact dedup call when contacts is empty
    fetchrows = [
        {"id": _INVESTOR_UUID},        # cross_ref name match
        None,                           # client_investor existing check
        {"id": _CLIENT_INVESTOR_UUID}, # client_investor INSERT
    ]
    conn = _transaction_conn(_make_fake_conn(fetchrows))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=payload)

    assert resp.status_code == 200
    assert resp.json()["data"]["contacts_upserted"] == 0


def test_ingest_bundle_cross_ref_match():
    """When investor is found in core table → investor_id returned."""
    conn = _transaction_conn(_make_fake_conn(_HAPPY_PATH_FETCHROWS))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    data = resp.json()["data"]
    assert data["investor_id"] == str(_INVESTOR_UUID)


def test_ingest_bundle_cross_ref_no_match():
    """No match in core investors → investor_id=null."""
    # name lookup miss — no website in payload, so only 1 cross_ref lookup
    fetchrows = [
        None,                           # cross_ref name miss
        None,                           # client_investor existing check
        {"id": _CLIENT_INVESTOR_UUID}, # client_investor INSERT
        None,                           # contact dedup
    ]
    conn = _transaction_conn(_make_fake_conn(fetchrows))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["investor_id"] is None


def test_ingest_bundle_all_interactions_inserted():
    """All interactions are inserted (no dedup in live schema)."""
    conn = _transaction_conn(_make_fake_conn(_HAPPY_PATH_FETCHROWS))
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.post("/ingest/investor-bundle", json=_BUNDLE_PAYLOAD)

    assert resp.status_code == 200
    assert resp.json()["data"]["interactions_upserted"] == 1


def test_gap_investors_returns_list():
    """Valid UUID client_id → 200, gap_investors list returned."""
    gap_rows = [
        {"firm_name": "a16z", "overall_score": 95, "investor_type": "vc"},
        {"firm_name": "Sequoia", "overall_score": 90, "investor_type": "vc"},
    ]
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=gap_rows)
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.get(f"/ingest/investor-gap/{_CLIENT_UUID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["total"] == 2
    assert body["data"]["client_id"] == str(_CLIENT_UUID)
    assert len(body["data"]["gap_investors"]) == 2
    assert body["data"]["gap_investors"][0]["firm_name"] == "a16z"


def test_gap_investors_no_db():
    """No DATABASE_URL → 503."""
    app = create_app()
    client = TestClient(app)

    resp = client.get(f"/ingest/investor-gap/{_CLIENT_UUID}")

    assert resp.status_code == 503


def test_gap_investors_invalid_client_id_returns_empty():
    """Non-UUID client_id → 200 with empty list (graceful degradation)."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.get("/ingest/investor-gap/not-a-uuid")

    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


def test_gap_investors_limit_param():
    """limit query param is forwarded to the DB query."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    client = _client_with_pool(_make_fake_pool(conn))

    resp = client.get(f"/ingest/investor-gap/{_CLIENT_UUID}?limit=5")

    assert resp.status_code == 200
    # Verify the limit value was passed as second positional arg to fetch (after SQL + client_uuid)
    call_args = conn.fetch.call_args
    assert call_args.args[2] == 5
