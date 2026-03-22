---
paths:
  - "app/**/*.py"
---
# FastAPI Patterns — investor-intel

## Endpoint Wiring
1. Pydantic models in `app/models/<endpoint>.py`
2. Service class in `app/services/<service>.py`, depends on `LlmClient` Protocol
3. DI factory in `app/main_deps.py`
4. Router in `app/api/routers/<endpoint>.py` with `rate_limit` dep
5. Register router in `app/main.py` `create_app()`

## Response Contract
All endpoints return `ApiResponse[T]` with fields: `success`, `request_id`, `data`, `error`

## LLM Integration
- `LlmClient` is a Protocol — add new methods there first
- Implement in `AnthropicLlmClient` with `_json_call` helper
- Return frozen dataclasses, not dicts
- Add fake implementation in `tests/conftest.py::_FakeLlmClient`

## Rate Limiting
- Rate limit: `Depends(rate_limit("<route_id>"))` — per IP, in-memory fixed window
- No API key auth — upstream N8N handles authentication
