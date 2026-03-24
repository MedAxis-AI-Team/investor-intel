---
paths:
  - "app/services/**/*.py"
  - "tests/**/*.py"
---
# LLM Output Contract — investor-intel

LLM responses are untrusted external input. Never rely on prompts alone to enforce exact values, enums, date formats, or fallback strings. All enforcement happens in code.

## Rules

### 1. Parse defensively
- `_json_call` must guard against empty text, markdown fences, and malformed JSON before `json.loads`
- Every field extracted from the LLM payload must have a type coercion (`int()`, `str()`, `float()`) or a `.get()` with a default
- Never pass raw LLM dicts to Pydantic models — extract and validate each field explicitly

### 2. Enum fields → code-level normalization
If a response field must be one of N exact values (e.g. `signal_type`, `confidence tier`):
- Define the canonical set as a `frozenset` or `Literal` in code
- Build a lookup table mapping common LLM synonyms to canonical values (e.g. `"fundraise"` → `"fund_close"`)
- Unknown values fall back to a safe default (e.g. `"other"`)
- Never rely on the prompt listing the enum — LLMs paraphrase

### 3. Exact-string fields → code-level enforcement
If a response field must contain an exact string under certain conditions (e.g. `suggested_contact = "Not identified"`):
- Validate the LLM output in code after parsing
- Use pattern matching (regex, keyword lists) to detect non-compliant values
- Replace with the required exact string programmatically

### 4. Computed fields → derive in code, not LLM
If a field can be derived deterministically (e.g. `expires_relevance = published_at + N days`):
- Compute it in Python — do not ask the LLM for date math, arithmetic, or lookups
- The LLM's job is judgment (scoring, analysis, rationale). Deterministic logic is code's job.

### 5. Content filtering → post-process in code
If certain terms must be absent from text fields under conditions (e.g. no FDA language for B2B clients):
- Keep the prompt instruction (defense in depth) but do NOT rely on it alone
- Add code-level validation or filtering as the enforcement layer
- Log violations for monitoring

### 6. Test fake alignment
When `_FakeLlmClient` in `tests/conftest.py` returns hardcoded values, those values must match the spec — not the raw LLM behavior. Update fakes whenever the spec changes.

## Checklist for new LLM-powered fields

Before shipping any new field that comes from LLM output:
- [ ] Is it an enum? → Add normalization map + fallback
- [ ] Is it an exact string? → Add code enforcement
- [ ] Is it computable? → Derive in code, ignore LLM value
- [ ] Is it free text with content rules? → Add post-processing filter
- [ ] Is the fake client returning a spec-compliant value?
