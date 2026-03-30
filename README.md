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
| `GET` | `/health` | none | Health check |
| `POST` | `/score-investors` | rate limited | 6-axis investor scoring with confidence tiers |
| `POST` | `/analyze-signal` | rate limited | Signal analysis (news, events, X/Grok posts). X_GROK source returns `x_signal_type`. |
| `POST` | `/generate-digest` | rate limited | Investor digest generation with `x_activity_section` for X signals |
| `POST` | `/score-grants` | rate limited | Grant opportunity scoring |
| `POST` | `/benchmark` | rate limited | Run accuracy evaluation against known investor-client pairs |

No API key required — N8N handles auth upstream.

### Example: score investors

```bash
curl -X POST http://localhost:8000/score-investors \
  -H "Content-Type: application/json" \
  -d '{
    "client": {
      "name": "NovaBio Therapeutics",
      "thesis": "CAR-T cell therapies for solid tumors",
      "geography": "US",
      "funding_target": "$15M Series A"
    },
    "investors": [
      { "name": "OrbiMed Advisors", "notes": "Healthcare VC, $23B+ AUM" },
      { "name": "Sequoia Capital", "notes": "Generalist VC" }
    ]
  }'
```

### Example: run benchmark via API

```bash
curl -X POST http://localhost:8000/benchmark \
  -H "Content-Type: application/json" \
  -d '{
    "sample_size": 3,
    "skip_url_check": true,
    "skip_consistency": true
  }'
```

**`BenchmarkRequest` fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sample_size` | `int \| null` | all | Limit to first N test cases |
| `skip_url_check` | `bool` | `true` | Skip HTTP HEAD reachability for evidence URLs |
| `skip_consistency` | `bool` | `true` | Skip repeat-run variance checks (saves LLM calls) |
| `consistency_runs` | `int` | `3` | Number of runs per case for consistency (2–10) |

## Tests

```bash
source venv/bin/activate

# Run all tests (128 total: 97 API + 31 benchmark)
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
    test_benchmark.py          #  5 tests — benchmark endpoint integration
    test_health.py             #  1 test
    test_rate_limit.py         #  1 test
    test_smoke.py              #  4 tests — realistic payloads, end-to-end shape
    test_bulletproof.py        # 58 tests — edge cases, validation, all endpoints
  benchmark/
    test_validators.py         # 14 tests — field, computation, URL validators
    test_confusion.py          #  6 tests — confusion matrix builder
    test_calibration.py        #  6 tests — confidence calibration + ECE
    test_reporter.py           #  5 tests — summary generation + trends
```

## Benchmarking

The benchmarking system evaluates investor scoring accuracy against known investor-client pairs. It tracks hit rates, validates outputs, and calibrates confidence scores.

### Run a benchmark

Requires a real `ANTHROPIC_API_KEY` in `.env`.

```bash
source venv/bin/activate

# Full evaluation (calls real LLM — all 10 dataset cases)
python -m benchmarks.cli --dataset benchmarks/dataset.json

# Fast run — skip URL reachability and consistency checks
python -m benchmarks.cli --skip-url-check --skip-consistency

# Run on first 3 cases only
python -m benchmarks.cli --sample-size 3 --skip-url-check --skip-consistency

# View summary of previous runs (no LLM calls)
python -m benchmarks.cli --summary-only

# Debug logging
python -m benchmarks.cli --verbose --skip-url-check --skip-consistency
```

### What it measures

| Metric | Description |
|--------|-------------|
| **Hit rate** | % of correct HIGH/MEDIUM/LOW tier predictions vs expected tiers (target: 30–50%) |
| **Confusion matrix** | Per-class precision, recall, F1 for tier classification |
| **Validation pass rate** | % of field, computation, and URL checks that pass |
| **Consistency** | Std dev across repeated runs per scoring axis (threshold: 15) |
| **Confidence calibration** | Expected Calibration Error (ECE) via Platt scaling (activates after 30+ samples) |

### Validators

| Validator | What it checks |
|-----------|---------------|
| `FieldValidator` | Score ranges (0–100), confidence (0.0–1.0), required string fields, evidence URL type |
| `ComputationValidator` | Weighted sum correctness, null sci_reg redistribution, evidence penalty logic |
| `UrlValidator` | Evidence URL format (urlparse); optional HTTP HEAD reachability (5s timeout) |
| `ConsistencyValidator` | Std dev per scoring axis across N LLM runs — flags if > 15 |

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--dataset` | `benchmarks/dataset.json` | Path to benchmark dataset |
| `--output` | `benchmarks/results/` | Results output directory |
| `--sample-size` | all | Limit to first N test cases |
| `--skip-url-check` | off | Skip HTTP HEAD reachability for evidence URLs |
| `--skip-consistency` | off | Skip repeat-run variance checks (saves LLM calls) |
| `--consistency-runs` | 3 | Number of runs per case for consistency |
| `--summary-only` | off | Print summary of previous runs only |
| `--verbose` | off | Debug logging |

Results are persisted to `benchmarks/results/` (gitignored). Exit code 1 if hit rate < 30%.

### Benchmark dataset

`benchmarks/dataset.json` — 10 cases with known investor-client pairs and expected score ranges/tiers:

| Cases | Scenario |
|-------|----------|
| 001, 003, 005, 007 | Strong fit (expected HIGH) |
| 002, 006 | Weak fit (expected LOW) |
| 004, 009 | Moderate fit (expected MEDIUM) |
| 008 | Edge case — no geography |
| 010 | Edge case — minimal investor info |

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
| `ENVIRONMENT` | `development` | `development` or `production` |
| `LLM_MODEL` | `claude-sonnet-4-20250514` | Claude model to use |
| `LLM_MAX_TOKENS` | `1024` | Max tokens per LLM response |
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
