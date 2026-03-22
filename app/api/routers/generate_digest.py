from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import rate_limit
from app.main_deps import get_digest_service
from app.models.common import ApiResponse
from app.models.generate_digest import GenerateDigestRequest, GenerateDigestResponse
from app.services.digest_service import DigestService

router = APIRouter(prefix="", tags=["phase-one"])


@router.post(
    "/generate-digest",
    response_model=ApiResponse[GenerateDigestResponse],
    dependencies=[Depends(rate_limit("generate-digest"))],
)
async def generate_digest(
    request: Request,
    req: GenerateDigestRequest,
    service: DigestService = Depends(get_digest_service),
) -> ApiResponse[GenerateDigestResponse]:
    result = await service.generate(req)
    request_id = getattr(request.state, "request_id", None)
    return ApiResponse(success=True, request_id=request_id, data=result)
