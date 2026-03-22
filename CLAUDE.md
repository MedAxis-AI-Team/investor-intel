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
- `app/api/routers/` — One router per endpoint: `score_investors`, `analyze_signal`, `generate_digest`, `score_grants`, `health`.
- `app/services/llm_client.py` — `LlmClient` Protocol + frozen dataclasses for LLM return types. All services depend on this abstraction.
- `app/services/anthropic_client.py` — Concrete `AnthropicLlmClient`. Sends structured prompts, parses raw JSON from Claude responses.
- `app/services/` — Business logic: `scoring_service` (6-axis weighted scoring + confidence), `signal_service`, `digest_service`, `grant_scoring_service`.
- `app/models/` — Pydantic request/response models. `common.py` has `ApiResponse[T]` generic wrapper used by all endpoints.

**Scoring model (6-axis):** thesis_alignment 30%, stage_fit 25%, check_size_fit 15%, scientific_regulatory_fit 15%, recency 10%, geography 5%. When scientific_regulatory_fit is null, its weight redistributes to thesis_alignment.

**Testing pattern:** `conftest.py` provides `_FakeLlmClient` that returns deterministic data. Tests override `get_llm_client` dependency — no real Anthropic calls.

**Deployment:** Render (see `render.yaml`). Health check at `/health`. Docs UI at `/` (root).

## Key Conventions

- All responses wrapped in `ApiResponse[T]` with `success`, `request_id`, `data`, `error` fields
- Confidence scoring: LLM raw score -> evidence penalty -> tier (HIGH/MEDIUM/LOW) via `ConfidencePolicy`
- Score weights are configurable via env vars and must sum to 1.0
- Frozen dataclasses for LLM return types, Pydantic models for API boundaries
- `from __future__ import annotations` in every file
- Always use `venv/` for running commands — never install packages globally

## Tracking

- **ADRs:** `.claude/docs/adr/` — Architectural Decision Records
- **Tasks:** `.claude/docs/tasks/` — Implementation task tracking
- **Decisions:** `.claude/docs/decisions/` — Session decision log
- **Git changelog:** Use `/git-log` command to generate change summaries
