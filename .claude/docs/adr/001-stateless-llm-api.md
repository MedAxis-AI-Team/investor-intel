# ADR-001: Stateless LLM-Powered API with Protocol-Based Abstraction
Date: 2026-03-22
Status: accepted

## Context
The investor intelligence system needs to score investors, analyze signals, generate digests, and score grants. These operations require LLM reasoning. The API is called from N8N workflows and must return structured data only — no delivery formatting.

## Decision
- Stateless FastAPI service with no database
- LLM integration via `LlmClient` Protocol pattern, concrete implementation in `AnthropicLlmClient`
- All LLM calls return frozen dataclasses; API boundaries use Pydantic models
- Confidence scoring is a post-LLM processing step with configurable thresholds
- Delivery-agnostic: API returns structured JSON, N8N handles formatting/delivery

## Consequences

### Positive
- Easy to test: swap `LlmClient` with `_FakeLlmClient` via DI
- Easy to switch LLM providers: implement new `LlmClient`
- No database migrations or state management
- Clear separation between intelligence and delivery

### Negative
- No caching: repeated identical requests hit the LLM every time
- In-memory rate limiter resets on restart
- Sequential investor scoring (not parallelized)

## Implementation Notes
- `app/services/llm_client.py` — Protocol + return type dataclasses
- `app/services/anthropic_client.py` — Concrete implementation
- `app/main_deps.py` — DI wiring
- `tests/conftest.py` — Fake client for testing
