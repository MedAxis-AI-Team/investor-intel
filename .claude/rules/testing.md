---
paths:
  - "tests/**/*.py"
---
# Testing — investor-intel

## Setup
- `conftest.py` sets `ENVIRONMENT=test`, `ANTHROPIC_API_KEY=test-anthropic-key`
- `get_settings.cache_clear()` runs before each test (autouse fixture)
- `_FakeLlmClient` overrides `get_llm_client` — no real Anthropic calls
- Always run tests via venv: `source venv/bin/activate && python -m pytest`

## Conventions
- Per-endpoint tests: `tests/api/test_<endpoint>.py`
- Cross-endpoint edge cases: `tests/api/test_bulletproof.py` (58 variance + validation tests)
- Smoke tests with realistic payloads: `tests/api/test_smoke.py`
- Benchmark infrastructure tests: `tests/benchmark/` (separate from API tests)
- No auth headers needed — auth is handled upstream by N8N
- Assert `ApiResponse` structure, not just status codes
- Test validation (422), rate limiting (429), and happy path (200)
- Coverage target: 80%+
