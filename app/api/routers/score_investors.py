from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import rate_limit
from app.main_deps import get_scoring_service
from app.models.common import ApiResponse
from app.models.score_investors import ScoreInvestorsRequest, ScoreInvestorsResponse
from app.services.scoring_service import ScoringService

router = APIRouter(prefix="", tags=["phase-one"])


@router.post(
    "/score-investors",
    response_model=ApiResponse[ScoreInvestorsResponse],
    dependencies=[Depends(rate_limit("score-investors"))],
)
async def score_investors(
    request: Request,
    req: ScoreInvestorsRequest,
    service: ScoringService = Depends(get_scoring_service),
) -> ApiResponse[ScoreInvestorsResponse]:
    result = await service.score_investors(req)
    request_id = getattr(request.state, "request_id", None)
    return ApiResponse(success=True, request_id=request_id, data=result)
