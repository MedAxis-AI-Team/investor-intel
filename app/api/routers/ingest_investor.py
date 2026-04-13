from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import rate_limit
from app.main_deps import get_ingest_service
from app.models.common import ApiResponse
from app.models.ingest_investor import (
    IngestInvestorBundleRequest,
    IngestInvestorBundleResponse,
    InvestorGapResponse,
)
from app.services.ingest_service import IngestService

router = APIRouter(prefix="/ingest", tags=["Ingestion"])


@router.post(
    "/investor-bundle",
    response_model=ApiResponse[IngestInvestorBundleResponse],
    dependencies=[Depends(rate_limit("ingest-bundle"))],
    summary="Ingest a client investor entry from their tracker",
    description=(
        "Atomically upserts an investor + contacts + interactions into the client pipeline "
        "(`client_investors`, `investor_contacts`, `investor_interactions`). "
        "Cross-references the core `investors` table by firm name or website. "
        "Requires `SUPABASE_CONNECTION_STRING` — returns 503 when DB is unavailable."
    ),
)
async def ingest_investor_bundle(
    request: Request,
    req: IngestInvestorBundleRequest,
    service: IngestService = Depends(get_ingest_service),
) -> ApiResponse[IngestInvestorBundleResponse]:
    result = await service.ingest_bundle(req)
    return ApiResponse(
        success=True,
        request_id=getattr(request.state, "request_id", None),
        data=result,
    )


@router.get(
    "/investor-gap/{client_id}",
    response_model=ApiResponse[InvestorGapResponse],
    dependencies=[Depends(rate_limit("ingest-gap"))],
    summary="Return investors not yet in a client's pipeline",
    description=(
        "Queries the core `investors` table for firms not already tracked by the given client. "
        "Useful for discovery gap analysis. `limit` defaults to 50, max 200. "
        "Requires `SUPABASE_CONNECTION_STRING`."
    ),
)
async def investor_gap(
    client_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    service: IngestService = Depends(get_ingest_service),
) -> ApiResponse[InvestorGapResponse]:
    result = await service.get_gap_investors(client_id, limit)
    return ApiResponse(
        success=True,
        request_id=getattr(request.state, "request_id", None),
        data=result,
    )
