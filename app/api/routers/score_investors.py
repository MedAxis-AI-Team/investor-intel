from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request

from app.api.deps import rate_limit
from app.main_deps import get_optional_ingest_service, get_scoring_service
from app.models.common import ApiResponse
from app.models.score_investors import InvestorInteractionBrief, ScoreInvestorsRequest, ScoreInvestorsResponse
from app.services.ingest_service import IngestService
from app.services.scoring_service import ScoringService

router = APIRouter(prefix="", tags=["phase-one"])

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def _normalize(name: str) -> str:
    return _NON_ALNUM.sub("", name.lower()).strip()


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
        client_map = {r.normalized_name: r for r in client_records}

        investor_sources = []
        investor_interactions = []
        for investor in req.investors:
            key = _normalize(investor.name)
            record = client_map.get(key)
            if record:
                investor_sources.append("client_provided")
                investor_interactions.append(list(record.interactions))
            else:
                investor_sources.append("discovery")
                investor_interactions.append([])

    result = await service.score_investors(
        req,
        investor_sources=investor_sources,
        investor_interactions=investor_interactions,
    )
    request_id = getattr(request.state, "request_id", None)
    return ApiResponse(success=True, request_id=request_id, data=result)
