from __future__ import annotations

import hashlib
import logging
import uuid

import asyncpg

from app.models.ingest_investor import (
    IngestInvestorBundleRequest,
    IngestInvestorBundleResponse,
    IngestInvestorInput,
    IngestContactInput,
    IngestInteractionInput,
    InvestorGapResponse,
    InvestorGapResult,
)

logger = logging.getLogger(__name__)


class IngestService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ingest_bundle(self, req: IngestInvestorBundleRequest) -> IngestInvestorBundleResponse:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                investor_id = await self._cross_ref_investor(conn, req.investor)
                client_investor_id = await self._upsert_client_investor(
                    conn, req.client_id, req.investor, investor_id
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
            needs_enrichment=(investor_id is None),
            contacts_upserted=contacts_upserted,
            interactions_upserted=interactions_upserted,
        )

    async def get_gap_investors(self, client_id: str, limit: int = 50) -> InvestorGapResponse:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.name, i.normalized_name, i.overall_score, i.investor_type
                FROM investors i
                WHERE NOT EXISTS (
                    SELECT 1 FROM client_investors ci
                    WHERE ci.client_id = $1
                      AND ci.normalized_name = i.normalized_name
                )
                ORDER BY i.overall_score DESC NULLS LAST
                LIMIT $2
                """,
                client_id,
                limit,
            )
        results = [InvestorGapResult(**dict(r)) for r in rows]
        return InvestorGapResponse(client_id=client_id, gap_investors=results, total=len(results))

    # ── Private helpers ────────────────────────────────────────────────────

    async def _cross_ref_investor(
        self, conn: asyncpg.Connection, investor: IngestInvestorInput
    ) -> uuid.UUID | None:
        row = await conn.fetchrow(
            "SELECT id FROM investors WHERE normalized_name = $1",
            investor.normalized_name,
        )
        if row:
            return row["id"]

        if investor.normalized_domain:
            row = await conn.fetchrow(
                "SELECT id FROM investors WHERE website ILIKE '%' || $1 || '%'",
                investor.normalized_domain,
            )
            if row:
                return row["id"]

        return None

    async def _upsert_client_investor(
        self,
        conn: asyncpg.Connection,
        client_id: str,
        investor: IngestInvestorInput,
        investor_id: uuid.UUID | None,
    ) -> uuid.UUID:
        row = await conn.fetchrow(
            """
            INSERT INTO client_investors (
                client_id, investor_id, investor_name, normalized_name, normalized_domain,
                investor_type, status, needs_enrichment, reported_deal_size,
                is_strategic, is_foundation, is_sovereign, is_crossover,
                internal_owner, source_file, raw_notes
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            ON CONFLICT (client_id, normalized_name) DO UPDATE SET
                investor_id         = EXCLUDED.investor_id,
                investor_name       = EXCLUDED.investor_name,
                normalized_domain   = EXCLUDED.normalized_domain,
                investor_type       = EXCLUDED.investor_type,
                status              = EXCLUDED.status,
                needs_enrichment    = EXCLUDED.needs_enrichment,
                reported_deal_size  = EXCLUDED.reported_deal_size,
                is_strategic        = EXCLUDED.is_strategic,
                is_foundation       = EXCLUDED.is_foundation,
                is_sovereign        = EXCLUDED.is_sovereign,
                is_crossover        = EXCLUDED.is_crossover,
                internal_owner      = EXCLUDED.internal_owner,
                source_file         = EXCLUDED.source_file,
                raw_notes           = EXCLUDED.raw_notes,
                updated_at          = now()
            RETURNING id
            """,
            client_id,
            investor_id,
            investor.investor_name,
            investor.normalized_name,
            investor.normalized_domain,
            investor.investor_type,
            investor.status,
            investor_id is None,
            investor.reported_deal_size,
            investor.is_strategic,
            investor.is_foundation,
            investor.is_sovereign,
            investor.is_crossover,
            investor.internal_owner,
            investor.source_file,
            investor.raw_notes,
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
            elif contact.name:
                existing = await conn.fetchrow(
                    "SELECT id FROM investor_contacts WHERE name = $1 AND client_investor_id = $2",
                    contact.name,
                    client_investor_id,
                )
                if existing:
                    continue

            await conn.execute(
                """
                INSERT INTO investor_contacts (client_investor_id, name, email, title, phone)
                VALUES ($1, $2, $3, $4, $5)
                """,
                client_investor_id,
                contact.name,
                contact.email,
                contact.title,
                contact.phone,
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
            segment_hash = (
                hashlib.md5(interaction.raw_segment.encode()).hexdigest()
                if interaction.raw_segment
                else None
            )
            result = await conn.execute(
                """
                INSERT INTO investor_interactions (
                    client_investor_id, event_date, event_type, summary,
                    outcome, decline_reason, next_step, raw_segment, segment_hash
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (
                    client_investor_id,
                    COALESCE(event_date, '1900-01-01'::date),
                    event_type,
                    COALESCE(segment_hash, '')
                ) DO NOTHING
                """,
                client_investor_id,
                interaction.event_date,
                interaction.event_type,
                interaction.summary,
                interaction.outcome,
                interaction.decline_reason,
                interaction.next_step,
                interaction.raw_segment,
                segment_hash,
            )
            if result == "INSERT 0 1":
                count += 1
        return count
