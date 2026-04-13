-- Migration 002: Add client_profile enum and modifiers to clients table
-- Applied to: Supabase live schema
-- Run date: April 2026
--
-- NOTE: The clients table exists in the live Supabase schema but is not
-- captured in migrations/001_*. Verify the table exists in the Supabase
-- dashboard before running. If it does not exist, create it first.

-- ---------------------------------------------------------------------------
-- Step 1: Create the enum type (idempotent via DO block)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'client_profile_type') THEN
        CREATE TYPE client_profile_type AS ENUM (
            'therapeutic',
            'medical_device',
            'diagnostics',
            'digital_health',
            'service_cro',
            'platform_tools'
        );
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Step 2: Add columns (idempotent via IF NOT EXISTS)
-- ---------------------------------------------------------------------------
ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS client_profile client_profile_type NOT NULL DEFAULT 'therapeutic',
    ADD COLUMN IF NOT EXISTS modifiers JSONB NOT NULL DEFAULT '[]'::jsonb;

-- ---------------------------------------------------------------------------
-- Step 3: Validate modifiers is always a JSON array
-- ---------------------------------------------------------------------------
ALTER TABLE clients
    DROP CONSTRAINT IF EXISTS clients_modifiers_is_array;

ALTER TABLE clients
    ADD CONSTRAINT clients_modifiers_is_array
    CHECK (jsonb_typeof(modifiers) = 'array');

-- ---------------------------------------------------------------------------
-- Step 4: Update existing rows (all existing clients default to 'therapeutic')
-- Already handled by DEFAULT above, but explicit for clarity.
-- ---------------------------------------------------------------------------
-- UPDATE clients SET client_profile = 'therapeutic' WHERE client_profile IS NULL;

-- Validation query (run manually to confirm):
-- SELECT client_profile, count(*) FROM clients GROUP BY client_profile;
