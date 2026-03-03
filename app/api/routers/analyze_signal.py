from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import rate_limit, require_api_key
from app.main_deps import get_signal_service
from app.models.analyze_signal import AnalyzeSignalRequest, AnalyzeSignalResponse
from app.models.common import ApiResponse
from app.services.signal_service import SignalService

router = APIRouter(prefix="", tags=["phase-one"])


@router.post(
    "/analyze-signal",
    response_model=ApiResponse[AnalyzeSignalResponse],
    dependencies=[Depends(require_api_key), Depends(rate_limit("analyze-signal"))],
)
async def analyze_signal(
    request: Request,
    req: AnalyzeSignalRequest,
    service: SignalService = Depends(get_signal_service),
) -> ApiResponse[AnalyzeSignalResponse]:
    result = await service.analyze(req)
    request_id = getattr(request.state, "request_id", None)
    return ApiResponse(success=True, request_id=request_id, data=result)
