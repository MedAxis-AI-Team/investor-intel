# Task: Layer 0 — Investor Intelligence API Build-Out
Date: 2026-04-20
Status: in-progress
Priority: P0
Related: [ADR-001](../adr/001-stateless-llm-api.md) | [ADR-002](../adr/002-profile-aware-scoring-config.md)

## Description

Build the stateless FastAPI service that powers MedAxis investor intelligence workflows.
Called from N8N — returns structured JSON only. Delivery (email, CRM, PDF) is downstream.

## Shipped (as of 2026-04-20)

### Core scoring pipeline
- [x] `/score-investors` — 6-axis weighted scoring (thesis_alignment 30%, stage_fit 25%, check_size_fit 15%, sci_reg 15%, recency 10%, geography 5%)
- [x] Dual DTO response — `results[]` (client-facing) + `advisor_data[]` (internal)
- [x] `scientific_regulatory_fit` gating via `needs_sci_reg()` for therapeutic profile
- [x] Grant-type stub — zero-score bypass, route to `/score-grants`
- [x] Angel-type confidence cap at MEDIUM
- [x] `investor_source` — `client_provided` vs `discovery` via DB cross-reference
- [x] `investor_tier` bucketing — Tier 1 (≥75), Tier 2 (≥60), Below Threshold (<60)
- [x] `dimension_strengths` — bucketed axis labels for client-facing display
- [x] `top_claims`, `narrative_summary`, `suggested_contact` in client response
- [x] Confidence scoring — `penalize_for_missing_evidence()` + `ConfidencePolicy`

### Profile-aware scoring (v0.2.0, shipped 2026-04-18)
- [x] `client_profile` enum — therapeutic (default), medical_device, diagnostics, digital_health, service_cro, platform_tools
- [x] `modifiers` array — ai_enabled, rpm_saas, cross_border_ca, ruo_no_reg
- [x] `ScoringInstructions` config-object pattern — no if/else chains, Phase 1.5 compatible
- [x] `score_scientific_regulatory` override — non-therapeutic profiles always score the axis
- [x] `_CLASSIFIER_VERSION` surfaced in `/health` response
- [x] Supabase migration `002_client_profile.sql` (reference SQL — not yet applied to live)

### Signal analysis
- [x] `/analyze-signal` — SEC_EDGAR, GOOGLE_NEWS, OTHER, X_GROK sources
- [x] X_GROK engagement-weighted scoring — replies, reposts, likes, is_original_post, author, author_type
- [x] `x_signal_type` normalization — fund_activity, thesis_statement, conference_signal, portfolio_mention, hiring_signal, general_activity
- [x] `expires_relevance` — derived in Python, not from LLM

### Digest generation
- [x] `/generate-digest` — dual digest: `client_digest` (email + X activity section) + `internal_digest` (advisor prep)
- [x] X activity section — structured signals sorted by window urgency
- [x] `LlmAdvisorPrep` — key_insights, outreach_angles, call_plan, likely_objections, risks_sensitivities, questions_to_ask
- [x] Pydantic guards for empty sections/threads/insights

### Grant scoring
- [x] `/score-grants` — 6-axis grant evaluation (therapeutic match, stage eligibility, award size, deadline feasibility, historical funding)

### Ingestion layer
- [x] `POST /ingest/investor-bundle` — atomic 3-table upsert (client_investors, investor_contacts, investor_interactions)
- [x] `GET /ingest/investor-gap/{client_id}` — discovery gap analysis
- [x] Cross-reference against core `investors` table by firm name / website
- [x] Graceful 503 when `SUPABASE_CONNECTION_STRING` not set

### Infrastructure
- [x] Rate limiting — in-memory fixed window per IP, configurable via env
- [x] `ApiResponse[T]` — generic wrapper with `success`, `request_id`, `data`, `error`
- [x] Request ID middleware — `X-Request-Id` header on every response
- [x] Structured logging with header redaction
- [x] Global exception handlers — validation_error (422), llm_timeout (504), held_for_review (200), internal_error (500)
- [x] `LlmRetryExhaustedError` → `held_for_review` code — flagged for manual review
- [x] Deployed on Render with `autoDeploy: true`
- [x] Health check at `/health` — status, version, scoring_classifier, db connectivity
- [x] Accuracy benchmark script — field-level LLM output validation against golden set

### LLM robustness
- [x] JSON extraction — handles preamble before fence, markdown fences, bare objects
- [x] Negated FDA term detection (e.g. "No FDA pathway" → `scientific_regulatory_fit=null`)
- [x] `enforce_suggested_contact()` — code-level enforcement of exact string
- [x] Enum normalization via lookup tables (`_llm_normalizers.py`) — no raw LLM enum values trusted

## Pending / Planned

### Phase 1.5 — Direct scoring_instructions injection
- [ ] Add optional `scoring_instructions: dict | None` to `ScoreInvestorsRequest`
- [ ] Parse into `ScoringInstructions` in router/service (additive tolerance — ignore unknown keys, fallback on failure, log `classifier_version`)
- [ ] Bypass `build_scoring_instructions()` when field is present
- [ ] Zero changes to `anthropic_client.py` prompt builder

### Signal → Score integration (post-Layer 0)
- [ ] Signals table data flowing into investor score modifiers (recency + sci_reg weight adjustments)
- [ ] Live signal context injection into `/score-investors` prompt for already-tracked investors
- [ ] Discussed with team 2026-04-20 — not prioritized for Layer 0

### Supabase migration
- [ ] Apply `migrations/002_client_profile.sql` to live Supabase schema
- [ ] Verify `client_profile` + `modifiers` columns on `clients` table

### Monitoring workflows integration
- [ ] SEC EDGAR, FDA, Federal Register monitoring workflows POST to `/analyze-signal` and write to signals table
- [ ] Signals table → Digest flow: N8N passes signals to `/generate-digest` via `signals[]` field
- [ ] Signals do not currently influence `/score-investors` composite scores (intentional for this phase)

## Notes

**Signals ↔ Scoring separation is intentional for Layer 0.** `/analyze-signal` and `/score-investors` are decoupled pipelines. Signals shape the Brief (digest) narrative and advisor prep. They do not modify composite scores in this phase. Score modifiers from live signal data are a post-Layer 0 design decision.

**`scientific_regulatory_fit` data source (current):** LLM knowledge + `investor_notes` field (enriched upstream via Perplexity or similar). Raw FDA/SEC signals from monitoring workflows do not pipe into the axis score directly yet.

**Migration 002 status:** Reference SQL written and reviewed. Not yet applied to live Supabase. Safe to apply — idempotent (DO block + IF NOT EXISTS). Confirm `clients` table exists in dashboard before running.
