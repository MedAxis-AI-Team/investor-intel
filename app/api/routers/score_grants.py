from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import rate_limit
from app.main_deps import get_grant_scoring_service
from app.models.common import ApiResponse
from app.models.score_grants import ScoreGrantsRequest, ScoreGrantsResponse
from app.services.grant_scoring_service import GrantScoringService

router = APIRouter(prefix="", tags=["Grant Scoring"])


@router.post(
    "/score-grants",
    response_model=ApiResponse[ScoreGrantsResponse],
    dependencies=[Depends(rate_limit("score-grants"))],
    summary="Score grant opportunities against a company profile",
    description=(
        "Evaluates one or more grant opportunities (NIH, NSF, SBIR/STTR, etc.) against "
        "a company's therapeutic area, stage, and FDA pathway. "
        "Returns per-grant scores across therapeutic match, stage eligibility, "
        "award size relevance, deadline feasibility, and historical funding alignment."
    ),
)
async def score_grants(
    request: Request,
    req: ScoreGrantsRequest,
    service: GrantScoringService = Depends(get_grant_scoring_service),
) -> ApiResponse[ScoreGrantsResponse]:
    result = await service.score_grants(req)
    request_id = getattr(request.state, "request_id", None)
    return ApiResponse(success=True, request_id=request_id, data=result)
