from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import ok, rate_limit
from app.main_deps import get_signal_service
from app.models.analyze_signal import AnalyzeSignalRequest, AnalyzeSignalResponse
from app.models.common import ApiResponse
from app.services.signal_service import SignalService

router = APIRouter(prefix="", tags=["Signal Analysis"])


@router.post(
    "/analyze-signal",
    response_model=ApiResponse[AnalyzeSignalResponse],
    dependencies=[Depends(rate_limit("analyze-signal"))],
    summary="Analyze an investor signal for relevance and priority",
    description=(
        "Scores a single signal (SEC filing, news article, or X/Grok post) for priority, "
        "rationale, and outreach angle against an investor and client context. "
        "`X_GROK` source enables engagement-weighted scoring and returns `x_signal_type` "
        "(fund_activity, thesis_statement, conference_signal, etc.). "
        "Other sources return `x_signal_type: null`."
    ),
)
async def analyze_signal(
    request: Request,
    req: AnalyzeSignalRequest,
    service: SignalService = Depends(get_signal_service),
) -> ApiResponse[AnalyzeSignalResponse]:
    result = await service.analyze(req)
    return ok(request, result)
