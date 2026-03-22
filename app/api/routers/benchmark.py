from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.api.deps import rate_limit
from app.config import Settings, get_settings
from app.main_deps import get_confidence_policy, get_llm_client, get_score_weights
from app.models.benchmark import BenchmarkRequest, BenchmarkResponse, CaseResultResponse
from app.models.common import ApiResponse
from app.services.confidence import ConfidencePolicy
from app.services.llm_client import LlmClient
from app.services.scoring_service import ScoreWeights

from benchmarks.runner import run_benchmark

router = APIRouter(prefix="", tags=["benchmarks"])

_DEFAULT_DATASET = Path("benchmarks/dataset.json")
_DEFAULT_OUTPUT = Path("benchmarks/results")


@router.post(
    "/benchmark",
    response_model=ApiResponse[BenchmarkResponse],
    dependencies=[Depends(rate_limit("benchmark"))],
)
async def run_benchmark_endpoint(
    request: Request,
    req: BenchmarkRequest,
    llm: LlmClient = Depends(get_llm_client),
    confidence_policy: ConfidencePolicy = Depends(get_confidence_policy),
    weights: ScoreWeights = Depends(get_score_weights),
    settings: Settings = Depends(get_settings),
) -> ApiResponse[BenchmarkResponse]:
    weights_dict = {
        "thesis_alignment": weights.thesis_alignment,
        "stage_fit": weights.stage_fit,
        "check_size_fit": weights.check_size_fit,
        "scientific_regulatory_fit": weights.scientific_regulatory_fit,
        "recency": weights.recency,
        "geography": weights.geography,
    }

    result = await run_benchmark(
        dataset_path=_DEFAULT_DATASET,
        output_dir=_DEFAULT_OUTPUT,
        settings=settings,
        llm=llm,
        confidence_policy=confidence_policy,
        weights=weights_dict,
        skip_url_check=req.skip_url_check,
        skip_consistency=req.skip_consistency,
        consistency_runs=req.consistency_runs,
        sample_size=req.sample_size,
    )

    response = BenchmarkResponse(
        run_id=result.run_id,
        timestamp=result.timestamp,
        total_cases=result.total_cases,
        hit_rate=result.hit_rate,
        validation_pass_rate=result.validation_pass_rate,
        confusion=result.confusion,
        calibration=result.calibration,
        case_results=[
            CaseResultResponse(
                test_case_id=cr.test_case_id,
                test_case_name=cr.test_case_name,
                score_snapshot=cr.score_snapshot,
                predicted_tier=cr.predicted_tier,
                expected_tier=cr.expected_tier,
                critical_failures=cr.critical_failures,
                warnings=cr.warnings,
                passed=cr.passed,
            )
            for cr in result.case_results
        ],
    )

    request_id = getattr(request.state, "request_id", None)
    return ApiResponse(success=True, request_id=request_id, data=response)
