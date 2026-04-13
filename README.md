# Investor Intelligence API

Stateless FastAPI service that provides LLM-powered investor intelligence. Called from N8N workflows (N8N handles auth upstream). Returns structured intelligence outputs only — delivery and formatting (HTML email, PDF reports, CRM writes, etc.) is handled downstream.

## Requirements

- Python 3.12+
- `ANTHROPIC_API_KEY` (for LLM calls)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then set ANTHROPIC_API_KEY
```

## Run

```bash
source venv/bin/activate
uvicorn app.main:app --reload
```

Docs UI at `/` (root). Health check at `/health`.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | Service status, API version, scoring classifier version, DB connectivity |
| `POST` | `/score-investors` | rate limited | 6-axis investor scoring with profile-aware prompt branching. Accepts `client_profile` + `modifiers`. Returns dual DTO: `results[]` (client-facing: `composite_score`, `investor_tier`, `dimension_strengths`, `top_claims`) + `advisor_data[]` (internal: `outreach_angle`, `full_axis_breakdown`). |
| `POST` | `/analyze-signal` | rate limited | Signal analysis (news, events, X/Grok posts). X_GROK source returns `x_signal_type`. |
| `POST` | `/generate-digest` | rate limited | Investor digest. Returns `client_digest` (email sections + `x_activity_section`) and `internal_digest` (advisor prep: `key_insights`, `call_plan`, `outreach_angles`, `likely_objections`). |
| `POST` | `/score-grants` | rate limited | Grant opportunity scoring |
| `POST` | `/ingest/investor-bundle` | rate limited | Ingest a client's investor entry (atomic 3-table upsert). Requires `SUPABASE_CONNECTION_STRING`. |
| `GET` | `/ingest/investor-gap/{client_id}` | rate limited | Top investors in core table not yet in client's pipeline. Requires `SUPABASE_CONNECTION_STRING`. |

No API key required — N8N handles auth upstream.

### Example: score investors

`client_profile` defaults to `"therapeutic"` if omitted. Supported profiles: `therapeutic`, `medical_device`, `diagnostics`, `digital_health`, `service_cro`, `platform_tools`. Supported modifiers: `ai_enabled`, `rpm_saas`, `cross_border_ca`, `ruo_no_reg`.

```bash
# Therapeutic (default)
curl -X POST http://localhost:8000/score-investors \
  -H "Content-Type: application/json" \
  -d '{
    "client": {
      "name": "NovaBio Therapeutics",
      "thesis": "CAR-T cell therapies for solid tumors. FDA IND filed.",
      "geography": "US",
      "funding_target": "$15M Series A"
    },
    "investors": [
      { "name": "OrbiMed Advisors", "notes": "Healthcare VC, $23B+ AUM" },
      { "name": "Sequoia Capital", "notes": "Generalist VC" }
    ]
  }'

# Digital health with modifiers
curl -X POST http://localhost:8000/score-investors \
  -H "Content-Type: application/json" \
  -d '{
    "client": {
      "name": "Predictive Healthcare",
      "thesis": "AI-enabled remote patient monitoring SaaS for chronic disease management.",
      "client_profile": "digital_health",
      "modifiers": ["ai_enabled", "rpm_saas"]
    },
    "investors": [
      { "name": "General Catalyst" },
      { "name": "7wireVentures" }
    ]
  }'
```

### Example: analyze X/Grok signal with engagement data

```bash
curl -X POST http://localhost:8000/analyze-signal \
  -H "Content-Type: application/json" \
  -d '{
    "signal_type": "X_GROK",
    "title": "OrbiMed partner posts about CAR-T investment thesis",
    "url": "https://x.com/orbimed_partner/status/123456789",
    "published_at": "2026-03-28",
    "raw_text": "Excited about the CAR-T space — seeing strong signals in solid tumor applications.",
    "investor": {
      "name": "Jonathan Silverstein",
      "firm": "OrbiMed Advisors",
      "thesis_keywords": ["CAR-T", "oncology", "cell therapy"],
      "portfolio_companies": ["Kymera", "Relay Therapeutics"]
    },
    "client": {
      "name": "NovaBio Therapeutics",
      "thesis": "CAR-T cell therapies for solid tumors",
      "geography": "US",
      "stage": "Series A"
    },
    "x_engagement_data": {
      "replies": 12,
      "reposts": 34,
      "likes": 210,
      "is_original_post": true,
      "author": "jonathan_silverstein",
      "author_type": "partner"
    }
  }'
```

Response includes `x_signal_type` (e.g. `"thesis_statement"`, `"fund_activity"`) for `X_GROK` signals; `null` for all other sources.

### Example: generate digest with X signals

```bash
curl -X POST http://localhost:8000/generate-digest \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "NovaBio Therapeutics",
    "week_start": "2026-03-24",
    "week_end": "2026-03-28",
    "signals": [
      { "title": "OrbiMed closes $600M fund", "url": "https://news.example.com/orbimed" }
    ],
    "investors": [
      { "name": "OrbiMed Advisors", "notes": "Lead investor candidate" }
    ],
    "x_signals": [
      {
        "investor_name": "Jonathan Silverstein",
        "firm": "OrbiMed Advisors",
        "signal_summary": "Partner posted about CAR-T thesis alignment",
        "x_signal_type": "thesis_statement",
        "recommended_action": "Send warm intro this week",
        "window": "this_week",
        "priority": "high"
      }
    ]
  }'
```

Response always includes `x_activity_section` with sorted signals (immediate → this_week → monitor). Empty when no `x_signals` provided.

### Example: ingest investor bundle

```bash
curl -X POST http://localhost:8000/ingest/investor-bundle \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "5b461960-3af1-4ae2-a733-c95e6a1ef04e",
    "investor": {
      "firm_name": "OrbiMed Advisors",
      "investor_type": "vc",
      "relationship_status": "active",
      "website": "orbimed.com"
    },
    "contacts": [
      {
        "full_name": "Jonathan Silverstein",
        "email": "jsilverstein@orbimed.com",
        "title": "Partner"
      }
    ],
    "interactions": [
      {
        "interaction_date": "2026-03-15",
        "interaction_type": "intro_via_third_party",
        "summary": "Initial call — strong thesis alignment on CAR-T",
        "outcome": "interested",
        "next_steps": "Send deck by March 20",
        "raw_note_excerpt": "Called Jonathan, discussed CAR-T pipeline..."
      }
    ]
  }'
```

`client_id` must be a valid UUID from the `clients` table. `relationship_status` accepts: `active`, `declined`, `dormant`, `new`. `interaction_type` accepts: `outreach`, `meeting`, `pitch`, `follow_up`, `decline`, `re_engagement`, `intro_via_third_party`, `data_room_access`, `term_sheet`.

Response:
```json
{
  "success": true,
  "data": {
    "client_investor_id": "uuid...",
    "investor_id": "uuid or null",
    "contacts_upserted": 1,
    "interactions_upserted": 1
  }
}
```

`investor_id` is non-null when the firm is matched to the core `investors` table (by firm name or website within the client's scope).

### Example: get gap investors

```bash
curl "http://localhost:8000/ingest/investor-gap/5b461960-3af1-4ae2-a733-c95e6a1ef04e?limit=10"
```

Returns the top investors in the core `investors` table (by `overall_score`) that are not yet in the client's pipeline.

## Tests

```bash
source venv/bin/activate

# Run all tests
python -m pytest

# Verbose output
python -m pytest -v

# Single file
python -m pytest tests/api/test_score_investors.py

# Single test
python -m pytest tests/api/test_score_investors.py::test_score_investors_returns_batch_results

# Coverage (80%+ required)
coverage run -m pytest && coverage report -m
```

Tests use a `_FakeLlmClient` — no real Anthropic calls are made.

### Test structure

```
tests/
  api/
    test_score_investors.py    #  5 tests — batch scoring, confidence, null sci_reg
    test_analyze_signal.py     # 10 tests — signal analysis, X_GROK, engagement data
    test_generate_digest.py    #  2 tests — digest structure + x_activity_section
    test_score_grants.py       #  9 tests — grant scoring, sorting, validation
    test_health.py             #  1 test
    test_rate_limit.py         #  1 test
    test_smoke.py              #  4 tests — realistic payloads, end-to-end shape
    test_bulletproof.py        # 58 tests — edge cases, validation, all endpoints
    test_ingest_investor.py    # 11 tests — ingestion bundle + gap analysis, fake pool
```

## Scoring Model

6-axis weighted scoring with configurable weights (must sum to 1.0):

| Axis | Default Weight |
|------|---------------|
| thesis_alignment | 0.30 |
| stage_fit | 0.25 |
| check_size_fit | 0.15 |
| scientific_regulatory_fit | 0.15 |
| recency | 0.10 |
| geography | 0.05 |

When `scientific_regulatory_fit` is null, its weight redistributes to `thesis_alignment`.

Confidence tiers: **HIGH** (≥ 0.8), **MEDIUM** (≥ 0.6), **LOW** (< 0.6). Missing evidence URLs apply a 0.25 penalty to confidence before tier assignment.

## Configuration

All config via environment variables. See `.env.example` for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required. Anthropic API key |
| `SUPABASE_CONNECTION_STRING` | — | Required for `/ingest/*` endpoints. Supabase Session Pooler URL (port 5432). Format: `postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres` |
| `GH_TOKEN` | — | Optional. GitHub token for GitHub data source |
| `XAI_API_KEY` | — | Optional. xAI API key for X/Grok signal source |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `LLM_MAX_TOKENS` | `4096` | Max tokens per LLM response |
| `REQUEST_TIMEOUT_SECONDS` | `20` | LLM call timeout |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window |
| `RATE_LIMIT_MAX_REQUESTS` | `60` | Max requests per window per IP |
| `CONFIDENCE_HIGH_THRESHOLD` | `0.8` | Min confidence for HIGH tier |
| `CONFIDENCE_MEDIUM_THRESHOLD` | `0.6` | Min confidence for MEDIUM tier |
| `EVIDENCE_MISSING_PENALTY` | `0.25` | Confidence penalty when no evidence URLs |
| `SCORE_WEIGHT_THESIS_ALIGNMENT` | `0.30` | Axis weight (all 6 must sum to 1.0) |
| `SCORE_WEIGHT_STAGE_FIT` | `0.25` | |
| `SCORE_WEIGHT_CHECK_SIZE_FIT` | `0.15` | |
| `SCORE_WEIGHT_SCIENTIFIC_REGULATORY_FIT` | `0.15` | |
| `SCORE_WEIGHT_RECENCY` | `0.10` | |
| `SCORE_WEIGHT_GEOGRAPHY` | `0.05` | |

## Deployment

Deployed on Render. See `render.yaml` for configuration.
