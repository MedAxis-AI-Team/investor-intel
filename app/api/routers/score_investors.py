from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import rate_limit
from app.main_deps import get_optional_ingest_service, get_scoring_service
from app.models.common import ApiResponse
from app.models.score_investors import InvestorInteractionBrief, ScoreInvestorsRequest, ScoreInvestorsResponse
from app.services.ingest_service import IngestService
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
    ingest: IngestService | None = Depends(get_optional_ingest_service),
) -> ApiResponse[ScoreInvestorsResponse]:
    investor_sources: list[str] | None = None
    investor_interactions: list[list[InvestorInteractionBrief]] | None = None

    if req.client_id and ingest is not None:
        client_records = await ingest.get_client_investors(req.client_id)
        investor_sources, investor_interactions = ScoringService.resolve_investor_context(
            req.investors, client_records
        )

    result = await service.score_investors(
        req,
        investor_sources=investor_sources,
        investor_interactions=investor_interactions,
    )
    request_id = getattr(request.state, "request_id", None)
    return ApiResponse(success=True, request_id=request_id, data=result)
