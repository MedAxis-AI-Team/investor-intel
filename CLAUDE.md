# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stateless FastAPI service (Python 3.12+) that provides LLM-powered investor intelligence. Called from N8N workflows (N8N handles auth upstream). Returns structured intelligence outputs only — delivery/formatting is handled downstream.

## Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then set ANTHROPIC_API_KEY

# Run
source venv/bin/activate && uvicorn app.main:app --reload

# Test (always use venv)
source venv/bin/activate && python -m pytest
source venv/bin/activate && python -m pytest tests/api/test_score_investors.py        # single file
source venv/bin/activate && python -m pytest tests/api/test_score_investors.py::test_x # single test
source venv/bin/activate && coverage run -m pytest && coverage report -m               # 80%+ required
```

## Architecture

**Request flow:** Router -> Rate limit (per IP) -> Service -> LlmClient (Protocol) -> AnthropicLlmClient

- `app/config.py` — `Settings` via pydantic-settings, cached with `@lru_cache`. All config from env vars.
- `app/main.py` — `create_app()` factory. Request-ID middleware, exception handlers, router registration.
- `app/main_deps.py` — FastAPI DI wiring. Builds services from settings. This is where LlmClient is swapped in tests.
- `app/api/deps.py` — Rate limiting (in-memory fixed window per IP). No API key auth (N8N handles upstream).
- `app/api/routers/` — One router per endpoint: `score_investors`, `analyze_signal`, `generate_digest`, `score_grants`, `health`, `ingest_investor`.
- `app/services/llm_client.py` — `LlmClient` Protocol + frozen dataclasses for LLM return types. All services depend on this abstraction.
- `app/services/anthropic_client.py` — Concrete `AnthropicLlmClient`. Sends structured prompts, parses raw JSON from Claude responses. `_build_profile_section()` injects `CLIENT PROFILE / PROFILE GUIDANCE / MODIFIER GUIDANCE` block from `ScoringInstructions`.
- `app/services/scoring_config.py` — `ScoringInstructions` frozen dataclass + `_PROFILE_CONFIGS` / `_MODIFIER_CONFIGS` lookup dicts + `build_scoring_instructions()`. Translates `client_profile` + `modifiers` into the config object that drives prompt construction. No if/else chains. Phase 1.5 compatible.
- `app/services/_llm_normalizers.py` — All LLM output normalization: enum lookup tables, expiry computation, FDA detection (`needs_sci_reg()`), contact enforcement. Extracted from `anthropic_client.py` per 600-line file limit.
- `app/services/` — Business logic: `scoring_service` (6-axis weighted scoring + confidence), `signal_service` (includes X/Grok signal analysis), `digest_service` (includes X activity section), `grant_scoring_service`.
- `app/services/ingest_service.py` — `IngestService(pool: asyncpg.Pool)`. Transactional 3-table upsert for client investor ingestion. `get_client_investors(client_id)` returns investor + interaction history for `/score-investors` consolidation. No LLM dependency.
- `app/models/` — Pydantic request/response models. `common.py` has `ApiResponse[T]` generic wrapper used by all endpoints. `ingest_investor.py` has ingestion models.

**Scoring model (6-axis):** thesis_alignment 30%, stage_fit 25%, check_size_fit 15%, scientific_regulatory_fit 15%, recency 10%, geography 5%. When scientific_regulatory_fit is null, its weight redistributes to thesis_alignment.

**Profile-aware scoring (`client_profile` + `modifiers`):** `ClientProfile` accepts `client_profile` (Literal enum, default `"therapeutic"`) and `modifiers` (list of modifier strings, default `[]`). `build_scoring_instructions()` translates these into a `ScoringInstructions` config object that branches the prompt without if/else chains. Profiles: `therapeutic` (default, preserves all existing behavior), `medical_device`, `diagnostics`, `digital_health`, `service_cro`, `platform_tools`. Modifiers (additive): `ai_enabled`, `rpm_saas`, `cross_border_ca`, `ruo_no_reg`. Non-therapeutic profiles set `score_scientific_regulatory=True`, which overrides `needs_sci_reg()` and always scores the axis (reframed per profile — device pathway, tech differentiation, etc.). The `_CLASSIFIER_VERSION` string (`"1.0.0-phase1"`) is logged with every run and returned by `/health` as `scoring_classifier`. See [ADR-002](docs/adr/002-profile-aware-scoring-config.md).

**Custom scoring policy (`scoring_policy`):** `ScoreInvestorsRequest` accepts an optional `scoring_policy: ScoringPolicy | None`. When supplied, it replaces `client_profile` + `modifiers` with request-level scoring control. When null, the legacy profile/modifiers path is used (fully backward compatible). `ScoringPolicy` structure: `policy_components` (1–6 `PolicyComponent` items, each with `axis` mapped to one of the 6 scoring axes, `weight: float`, optional `guidance: str` max 300 chars, optional `soft_boosts`), `hard_exclusions` (global gate — if any `match_term` substring matches `investor.name + notes + investor_type`, `composite_score = 0`, checked before any axis computation), `capital_channels` (post-scoring multipliers, applied after weighted sum). Scoring math: (1) check hard exclusions first, (2) apply `soft_boosts` at component level before weighted sum (`boosted_score = min(100, raw * multiplier)`), (3) compute weighted sum normalizing weights to sum=1.0 server-side (logged if adjustment needed), (4) apply `capital_channels` multipliers post-sum. Freeform fields (`guidance`, `reason`) are sanitized at parse time: markdown stripped, URLs removed, prompt injection patterns trigger `ValidationError` (patterns: `ignore previous`, `system:`, angle brackets, `{{`, `jailbreak`, `bypass`, `override`). `scoring_policy` is received as `dict | None` and validated lazily in `_parse_scoring_policy()` — `ValidationError` logs the full payload and falls back to the `client_profile` + `modifiers` path, returning 200 with `version_bundle.scoring_policy_version = "fallback"` instead of 422. `_policy_to_instructions()` in `scoring_service.py` converts `ScoringPolicy` → `ScoringInstructions` for the LLM prompt builder. `ScoringPolicy` accepts an optional `version: str` field (default `"1.0"`) echoed in `version_bundle`. Ref: Addendum F v2.3 Sections 2.1, 2.2, 2.4.

**Version bundle (`version_bundle`):** Every `/score-investors` response includes a `version_bundle: VersionBundle` object logged at service entry and written to `ScoreInvestorsResponse.version_bundle`. Fields: `scoring_policy_version` (`policy.version` when policy valid, `"fallback"` when policy parse fails, `"none"` when no policy supplied), `endpoint_version` (from `app.__version__`), `prompt_version` (from `_CLASSIFIER_VERSION`), `model_version` (from `settings.llm_model`). Ref: Addendum F v2.3 Section 9.

**Signal ↔ Score pipeline separation (intentional, Layer 0):** `/analyze-signal` and `/score-investors` are decoupled pipelines. Signals shape the Brief (digest narrative, advisor prep) via `/generate-digest`. They do not modify composite investor scores. Live signal → score integration (recency/sci_reg weight adjustments from FDA clearances, SEC filings) is a post-Layer 0 design decision.

**Dual DTO pattern (`/score-investors`):** Response includes two parallel lists:
- `results: list[InvestorScore]` — client-facing: `composite_score`, `investor_tier`, `investor_source`, `dimension_strengths`, `narrative_summary`, `top_claims`, `interactions`, `confidence`, `suggested_contact`, `evidence_urls`.
- `advisor_data: list[InvestorAdvisorScore]` — internal: `outreach_angle`, `avoid`, `full_axis_breakdown` (raw 0–100 axis scores), `notes`, `re_engagement_notes`.

**investor_tier thresholds (computed in code, not LLM):** composite_score ≥75 → "Tier 1" · ≥60 → "Tier 2" · <60 → "Below Threshold".

**Dimension mapping (internal axis → client label, bucketed in code):**
| Internal axis | Client label |
|---|---|
| thesis_alignment | strategic_fit |
| stage_fit | stage_relevance |
| check_size_fit | capital_alignment |
| scientific_regulatory_fit | scientific_depth (null if not scored) |
| recency | market_activity |
| geography | geographic_proximity |

Bucketing: raw ≥70 → "High" · ≥45 → "Medium" · <45 → "Low". Implemented in `_llm_normalizers.bucket_score()`.

**investor_source consolidation:** When `client_id` is provided in the request and `DATABASE_URL` is set, the `/score-investors` router queries `client_investors` to tag each investor as `"client_provided"` (matched) or `"discovery"` (not in tracker). Degrades gracefully to `"discovery"` for all when DB is unavailable.

**Dual response (`/generate-digest`):** Returns `client_digest: DigestPayload` (email sections + x_activity_section) and `internal_digest: AdvisorPrepPayload` (key_insights, outreach_angles, call_plan, likely_objections, risks_sensitivities, questions_to_ask) — both from a single LLM call.

**Testing pattern:** `conftest.py` provides `_FakeLlmClient` that returns deterministic data. Tests override `get_llm_client` dependency — no real Anthropic calls.

**Error handling:** Global catch-all exception handler returns structured `ApiResponse` with `internal_error` code for any unhandled exception. LLM JSON parsing strips markdown code fences and guards against empty responses before `json.loads`.

**Signal source types:** `SEC_EDGAR`, `GOOGLE_NEWS`, `OTHER`, `X_GROK`. When `signal_type == "X_GROK"`, the signal prompt includes X-specific engagement/content weighting and returns `x_signal_type` (thesis_statement, conference_signal, fund_activity, portfolio_mention, hiring_signal, general_activity). Non-X_GROK sources return `x_signal_type: null`. Request accepts `x_engagement_data` (replies, reposts, likes, is_original_post, author, author_type) for structured engagement metric injection into the prompt. `SignalInvestorContext` includes `firm`, `SignalClientContext` includes `stage`.

**Digest X activity section:** `/generate-digest` always returns `x_activity_section` with structured signals (investor_name, firm, signal_summary, x_signal_type, recommended_action, window, priority) sorted by window urgency. Empty state: `signals: [], section_note: "No X signals recorded this week."`.

**LLM output contract** (`.claude/rules/llm-output-contract.md`): LLM responses are untrusted. Enum fields are normalized via lookup tables, exact-string fields are enforced by regex, computable fields (dates, arithmetic) are derived in Python — never from LLM output. Prompt instructions are defense-in-depth only. `x_signal_type`, `window`, and `priority` fields are all code-normalized via lookup tables.

**Ingestion layer:** `POST /ingest/investor-bundle` accepts a client's existing investor tracker entry (investor + contacts + interactions) and writes atomically to `client_investors`, `investor_contacts`, `investor_interactions` via a single Postgres transaction. Cross-references against the core `investors` table by firm_name (ILIKE) then website within the same client's scope — `investor_id` is null when no match. `GET /ingest/investor-gap/{client_id}` returns investors in the core table not yet in the client's pipeline. `client_id` must be a valid UUID. DB layer requires `SUPABASE_CONNECTION_STRING` env var (Supabase Session Pooler, port 5432). Omitting it disables the ingest endpoints with 503. Tables: `client_investors`, `investor_contacts`, `investor_interactions`, `ingestion_errors` (dead-letter, written by n8n directly, not the bundle endpoint). Migration `migrations/001_client_investor_ingestion.sql` is reference only — live schema may differ.

**Deployment:** Render (see `render.yaml`). `autoDeploy: true` on main branch. Health check at `/health` — returns `status`, `version`, `scoring_classifier`, `db`. Docs UI at `/` (root). Current deployed version: `0.2.0`.

**Agents** (`.claude/agents/`): `code-reviewer` (post-edit review), `security-reviewer` (pre-commit security), `tdd-guide` (test-driven dev), `planner` (implementation planning), `build-error-resolver` (fix build failures), `issue-triager` (priority triage on changes), `git-workflow` (branch/commit/PR/merge lifecycle), `llm-contract-validator` (validates LLM output fields have code enforcement).

## Key Conventions

- All responses wrapped in `ApiResponse[T]` with `success`, `request_id`, `data`, `error` fields
- Confidence scoring: LLM raw score -> evidence penalty -> tier (HIGH/MEDIUM/LOW) via `ConfidencePolicy`
- Score weights are configurable via env vars and must sum to 1.0
- Frozen dataclasses for LLM return types, Pydantic models for API boundaries
- `from __future__ import annotations` in every file
- Always use `venv/` for running commands — never install packages globally
- **Keep docs in sync:** When modifying files, always update relevant documentation (`CLAUDE.md`, `README.md`, architecture specs in `.claude/docs/`) to reflect the changes. See `.claude/rules/docs-sync.md` for details.

## Slash Commands

| Command | File | Description |
|---------|------|-------------|
| `/git-log` | `.claude/commands/git-log.md` | Generate a git changelog summary for a date range |
| `/adr` | `.claude/commands/adr.md` | Create a new Architectural Decision Record in `.claude/docs/adr/` |
| `/decision` | `.claude/commands/decision.md` | Log a session decision in `.claude/docs/decisions/` |
| `/status` | `.claude/commands/status.md` | Print current branch, open PRs, and recent commit summary |

## Tracking

- **ADRs:** `.claude/docs/adr/` — Architectural Decision Records
  - `001-stateless-llm-api.md` — Core stateless FastAPI + Protocol pattern
  - `002-profile-aware-scoring-config.md` — client_profile + modifiers, ScoringInstructions, Phase 1.5 compat
- **Tasks:** `.claude/docs/tasks/` — Implementation task tracking
  - `layer0-status.md` — Full Layer 0 build-out: shipped vs. pending (updated 2026-04-20)
- **Decisions:** `.claude/docs/decisions/` — Session decision log
- **Git changelog:** Use `/git-log` command to generate change summaries
