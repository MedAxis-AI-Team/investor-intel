from __future__ import annotations

from pydantic import BaseModel, Field


class BenchmarkRequest(BaseModel):
    sample_size: int | None = Field(
        default=None,
        ge=1,
        description="Run on first N test cases only (default: all)",
    )
    skip_url_check: bool = Field(
        default=True,
        description="Skip HTTP reachability checks for evidence URLs",
    )
    skip_consistency: bool = Field(
        default=True,
        description="Skip consistency validation (saves LLM calls)",
    )
    consistency_runs: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Number of runs per case for consistency checks",
    )


class CaseResultResponse(BaseModel):
    test_case_id: str
    test_case_name: str
    score_snapshot: dict
    predicted_tier: str
    expected_tier: str | None
    critical_failures: int
    warnings: int
    passed: int


class BenchmarkResponse(BaseModel):
    run_id: str
    timestamp: str
    total_cases: int
    hit_rate: float | None
    validation_pass_rate: float
    confusion: dict | None = None
    calibration: dict | None = None
    case_results: list[CaseResultResponse]
