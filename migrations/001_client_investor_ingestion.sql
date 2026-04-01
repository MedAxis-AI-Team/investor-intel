-- Migration 001: Client Investor List Ingestion
-- Adds 4 tables for ingesting client investor trackers.
-- Run against Supabase Postgres: psql $DATABASE_URL -f migrations/001_client_investor_ingestion.sql

-- ============================================================
-- updated_at trigger function (shared)
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Table: client_investors
-- One row per investor per client. Links to core investors table
-- when a cross-reference match is found.
-- ============================================================
CREATE TABLE IF NOT EXISTS client_investors (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id           TEXT NOT NULL,
    investor_id         UUID REFERENCES investors(id) NULL,  -- NULL if unmatched
    investor_name       TEXT NOT NULL,
    normalized_name     TEXT NOT NULL,
    normalized_domain   TEXT NULL,
    investor_type       TEXT NOT NULL DEFAULT 'vc'
        CHECK (investor_type IN ('vc','cvc','angel','family_office','grant','accelerator','other')),
    status              TEXT NOT NULL
        CHECK (status IN ('active','declined','dormant','new')),
    needs_enrichment    BOOLEAN NOT NULL DEFAULT true,
    reported_deal_size  TEXT NULL,
    is_strategic        BOOLEAN NOT NULL DEFAULT false,
    is_foundation       BOOLEAN NOT NULL DEFAULT false,
    is_sovereign        BOOLEAN NOT NULL DEFAULT false,
    is_crossover        BOOLEAN NOT NULL DEFAULT false,
    internal_owner      TEXT NULL,
    source_file         TEXT NULL,
    raw_notes           TEXT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_investors_client_name UNIQUE (client_id, normalized_name)
);

CREATE INDEX IF NOT EXISTS idx_ci_investor_id
    ON client_investors (investor_id);

CREATE INDEX IF NOT EXISTS idx_ci_normalized_domain
    ON client_investors (normalized_domain)
    WHERE normalized_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ci_client_status_type
    ON client_investors (client_id, status, investor_type);

CREATE INDEX IF NOT EXISTS idx_ci_needs_enrichment
    ON client_investors (needs_enrichment)
    WHERE needs_enrichment = true;

CREATE TRIGGER trg_client_investors_updated_at
    BEFORE UPDATE ON client_investors
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- Table: investor_contacts
-- Contacts associated with a client investor record.
-- Deduped on email (preferred) or name + client_investor_id.
-- ============================================================
CREATE TABLE IF NOT EXISTS investor_contacts (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_investor_id   UUID NOT NULL REFERENCES client_investors(id) ON DELETE CASCADE,
    name                 TEXT NULL,
    email                TEXT NULL,
    title                TEXT NULL,
    phone                TEXT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ic_client_investor
    ON investor_contacts (client_investor_id);

CREATE INDEX IF NOT EXISTS idx_ic_email
    ON investor_contacts (email)
    WHERE email IS NOT NULL;

-- ============================================================
-- Table: investor_interactions
-- Parsed interaction timeline entries extracted from CRM notes.
-- Deduped on composite key to prevent double-ingestion on re-upload.
-- ============================================================
CREATE TABLE IF NOT EXISTS investor_interactions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_investor_id   UUID NOT NULL REFERENCES client_investors(id) ON DELETE CASCADE,
    event_date           DATE NULL,
    event_type           TEXT NOT NULL
        CHECK (event_type IN (
            'outreach','meeting','pitch','follow_up','decline',
            're_engagement','intro_via_third_party','data_room_access','term_sheet'
        )),
    summary              TEXT NOT NULL,
    outcome              TEXT NULL
        CHECK (outcome IS NULL OR outcome IN (
            'pending','interested','rejected','conditional','timing_dependent'
        )),
    decline_reason       TEXT NULL
        CHECK (decline_reason IS NULL OR decline_reason IN (
            'stage_mismatch','thesis_mismatch','portfolio_conflict',
            'no_clinical_data','fund_timing','prioritization','team_mismatch',
            'differentiation_weak','market_risk','regulatory_risk','valuation_mismatch'
        )),
    next_step            TEXT NULL,
    raw_segment          TEXT NULL,
    segment_hash         TEXT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dedup index: prevents re-ingesting the same interaction on re-upload
CREATE UNIQUE INDEX IF NOT EXISTS idx_ii_dedup
    ON investor_interactions (
        client_investor_id,
        COALESCE(event_date, '1900-01-01'::date),
        event_type,
        COALESCE(segment_hash, '')
    );

CREATE INDEX IF NOT EXISTS idx_ii_client_investor
    ON investor_interactions (client_investor_id);

CREATE INDEX IF NOT EXISTS idx_ii_event_date
    ON investor_interactions (event_date)
    WHERE event_date IS NOT NULL;

-- ============================================================
-- Table: ingestion_errors (dead-letter queue)
-- Written directly by Stephen's n8n workflow on row-level failures.
-- NOT written through the /ingest/investor-bundle endpoint.
-- ============================================================
CREATE TABLE IF NOT EXISTS ingestion_errors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       TEXT NOT NULL,
    batch_index     INT NULL,
    row_index       INT NULL,
    raw_input       JSONB NOT NULL,
    raw_llm_output  TEXT NULL,
    error_type      TEXT NOT NULL,
    resolved        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ie_client_id
    ON ingestion_errors (client_id);

CREATE INDEX IF NOT EXISTS idx_ie_unresolved
    ON ingestion_errors (resolved, created_at)
    WHERE resolved = false;
