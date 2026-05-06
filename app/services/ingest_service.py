from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

import asyncpg

from app.models.ingest_investor import (
    IngestContactInput,
    IngestInteractionInput,
    IngestInvestorBundleRequest,
    IngestInvestorBundleResponse,
    IngestInvestorInput,
    InvestorGapResponse,
    InvestorGapResult,
)
from app.models.score_investors import InvestorInteractionBrief

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClientInvestorRecord:
    firm_name: str
    investor_type: str
    relationship_status: str
    interactions: list[InvestorInteractionBrief] = field(default_factory=list)


class IngestService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ingest_bundle(self, req: IngestInvestorBundleRequest) -> IngestInvestorBundleResponse:
        client_uuid = _parse_uuid(req.client_id)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                investor_id = await self._cross_ref_investor(conn, client_uuid, req.investor)
                client_investor_id = await self._upsert_client_investor(
                    conn, client_uuid, req.investor, investor_id
                )
                contacts_upserted = await self._upsert_contacts(
                    conn, client_investor_id, req.contacts
                )
                interactions_upserted = await self._upsert_interactions(
                    conn, client_investor_id, req.interactions
                )

        return IngestInvestorBundleResponse(
            client_investor_id=str(client_investor_id),
            investor_id=str(investor_id) if investor_id else None,
            contacts_upserted=contacts_upserted,
            interactions_upserted=interactions_upserted,
        )

    async def get_gap_investors(self, client_id: str, limit: int = 50) -> InvestorGapResponse:
        client_uuid = _parse_uuid(client_id)
        if client_uuid is None:
            return InvestorGapResponse(client_id=client_id, gap_investors=[], total=0)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.firm_name, i.overall_score, i.investor_type
                FROM investors i
                WHERE i.client_id = $1
                  AND NOT EXISTS (
                    SELECT 1 FROM client_investors ci
                    WHERE ci.client_id = $2
                      AND ci.investor_name ILIKE i.firm_name
                  )
                ORDER BY i.overall_score DESC NULLS LAST
                LIMIT $3
                """,
                client_uuid,
                str(client_uuid),
                limit,
            )
        results = [InvestorGapResult(**dict(r)) for r in rows]
        return InvestorGapResponse(client_id=client_id, gap_investors=results, total=len(results))

    async def get_client_investors(self, client_id: str) -> list[ClientInvestorRecord]:
        """Return all investors in a client's tracker with their interaction history."""
        client_uuid = _parse_uuid(client_id)
        if client_uuid is None:
            return []

        async with self._pool.acquire() as conn:
            investor_rows = await conn.fetch(
                """
                SELECT id, investor_name, investor_type, status
                FROM client_investors
                WHERE client_id = $1
                ORDER BY investor_name
                """,
                str(client_uuid),
            )
            records = []
            for row in investor_rows:
                interaction_rows = await conn.fetch(
                    """
                    SELECT event_date, event_type, summary, outcome
                    FROM investor_interactions
                    WHERE client_investor_id = $1
                    ORDER BY event_date DESC NULLS LAST
                    LIMIT 10
                    """,
                    row["id"],
                )
                interactions = [
                    InvestorInteractionBrief(
                        date=ir["event_date"],
                        event_type=ir["event_type"],
                        summary=ir["summary"],
                        outcome=ir["outcome"],
                    )
                    for ir in interaction_rows
                ]
                records.append(ClientInvestorRecord(
                    firm_name=str(row["investor_name"]),
                    investor_type=str(row["investor_type"] or "vc"),
                    relationship_status=str(row["status"] or "new"),
                    interactions=interactions,
                ))
        return records

    # ── Private helpers ────────────────────────────────────────────────────

    async def _cross_ref_investor(
        self,
        conn: asyncpg.Connection,
        client_uuid: uuid.UUID | None,
        investor: IngestInvestorInput,
    ) -> uuid.UUID | None:
        # investors.client_id is uuid — pass UUID object directly
        if client_uuid is None:
            return None

        row = await conn.fetchrow(
            "SELECT id FROM investors WHERE client_id = $1 AND firm_name ILIKE $2",
            client_uuid,
            investor.firm_name,
        )
        if row:
            return row["id"]

        if investor.website:
            row = await conn.fetchrow(
                "SELECT id FROM investors WHERE client_id = $1 AND website ILIKE '%' || $2 || '%'",
                client_uuid,
                investor.website,
            )
            if row:
                return row["id"]

        return None

    async def _upsert_client_investor(
        self,
        conn: asyncpg.Connection,
        client_uuid: uuid.UUID | None,
        investor: IngestInvestorInput,
        investor_id: uuid.UUID | None,
    ) -> uuid.UUID:
        # client_investors.client_id is text — always pass as string
        if client_uuid is not None:
            existing = await conn.fetchrow(
                "SELECT id FROM client_investors WHERE client_id = $1 AND investor_name ILIKE $2 FOR UPDATE",
                str(client_uuid),
                investor.investor_name or investor.firm_name,
            )
        else:
            existing = None

        if existing:
            row = await conn.fetchrow(
                """
                UPDATE client_investors SET
                    investor_id   = COALESCE($1, investor_id),
                    investor_name = COALESCE($2, investor_name),
                    investor_type = $3,
                    status        = COALESCE($4, status),
                    raw_notes     = COALESCE($5, raw_notes)
                WHERE id = $6
                RETURNING id
                """,
                investor_id,
                investor.investor_name,
                investor.investor_type,
                investor.relationship_status,
                investor.notes,
                existing["id"],
            )
            return row["id"]

        row = await conn.fetchrow(
            """
            INSERT INTO client_investors (
                client_id, investor_id, investor_name,
                investor_type, status, raw_notes
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            str(client_uuid),
            investor_id,
            investor.investor_name or investor.firm_name,
            investor.investor_type,
            investor.relationship_status,
            investor.notes,
        )
        return row["id"]

    async def _upsert_contacts(
        self,
        conn: asyncpg.Connection,
        client_investor_id: uuid.UUID,
        contacts: list[IngestContactInput],
    ) -> int:
        count = 0
        for contact in contacts:
            if contact.email:
                existing = await conn.fetchrow(
                    "SELECT id FROM investor_contacts WHERE email = $1 AND client_investor_id = $2",
                    contact.email,
                    client_investor_id,
                )
                if existing:
                    continue
            elif contact.full_name:
                existing = await conn.fetchrow(
                    "SELECT id FROM investor_contacts WHERE name = $1 AND client_investor_id = $2",
                    contact.full_name,
                    client_investor_id,
                )
                if existing:
                    continue

            await conn.execute(
                """
                INSERT INTO investor_contacts (
                    client_investor_id, name, email, title
                ) VALUES ($1, $2, $3, $4)
                """,
                client_investor_id,
                contact.full_name,
                contact.email,
                contact.title,
            )
            count += 1
        return count

    async def _upsert_interactions(
        self,
        conn: asyncpg.Connection,
        client_investor_id: uuid.UUID,
        interactions: list[IngestInteractionInput],
    ) -> int:
        count = 0
        for interaction in interactions:
            await conn.execute(
                """
                INSERT INTO investor_interactions (
                    client_investor_id, event_date, event_type,
                    summary, outcome, decline_reason, next_step, raw_segment
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                client_investor_id,
                interaction.interaction_date,
                interaction.interaction_type,
                interaction.summary,
                interaction.outcome,
                interaction.decline_reason,
                interaction.next_steps,
                interaction.raw_note_excerpt,
            )
            count += 1
        return count


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
