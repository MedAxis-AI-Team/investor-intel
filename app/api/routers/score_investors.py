from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import ok, rate_limit
from app.main_deps import get_optional_ingest_service, get_scoring_service
from app.models.common import ApiResponse
from app.models.score_investors import InvestorInteractionBrief, ScoreInvestorsRequest, ScoreInvestorsResponse
from app.services.ingest_service import IngestService
from app.services.scoring_service import ScoringService

router = APIRouter(prefix="", tags=["Investor Scoring"])


@router.post(
    "/score-investors",
    response_model=ApiResponse[ScoreInvestorsResponse],
    dependencies=[Depends(rate_limit("score-investors"))],
    summary="Score a list of investors against a client profile",
    description=(
        "Runs 6-axis weighted scoring (thesis alignment, stage fit, check size, "
        "scientific/regulatory fit, recency, geography) for each investor. "
        "Accepts `client_profile` (`therapeutic`, `medical_device`, `diagnostics`, "
        "`digital_health`, `service_cro`, `platform_tools`) and optional `modifiers` "
        "(`ai_enabled`, `rpm_saas`, `cross_border_ca`, `ruo_no_reg`) to branch the scoring prompt. "
        "Returns a dual DTO: `results[]` (client-facing composite score, tier, dimension strengths) "
        "and `advisor_data[]` (internal axis breakdown, outreach angle, avoid notes)."
    ),
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
    return ok(request, result)
