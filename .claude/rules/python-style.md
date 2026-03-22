---
paths:
  - "**/*.py"
---
# Python Style — investor-intel

- `from __future__ import annotations` at top of every file
- Frozen dataclasses for internal value objects (LLM return types)
- Pydantic `BaseModel` for API request/response boundaries
- Type hints on all public functions; `str | None` union syntax (not `Optional`)
- No `print()` — use `logging.getLogger(__name__)`
- Config via env vars through `pydantic-settings`, never hardcoded
- Always use the project `venv/` for running commands: `source venv/bin/activate && <command>`. Never install packages globally.
