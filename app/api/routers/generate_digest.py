from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import ok, rate_limit
from app.main_deps import get_digest_service
from app.models.common import ApiResponse
from app.models.generate_digest import GenerateDigestRequest, GenerateDigestResponse
from app.services.digest_service import DigestService

router = APIRouter(prefix="", tags=["Digest"])


@router.post(
    "/generate-digest",
    response_model=ApiResponse[GenerateDigestResponse],
    dependencies=[Depends(rate_limit("generate-digest"))],
    summary="Generate a weekly investor digest for a client",
    description=(
        "Produces a dual digest from a single LLM call: "
        "`client_digest` (email sections + structured X activity section) "
        "and `internal_digest` (advisor prep: key insights, call plan, outreach angles, "
        "likely objections, risks, questions to ask). "
        "X activity signals are sorted by window urgency."
    ),
)
async def generate_digest(
    request: Request,
    req: GenerateDigestRequest,
    service: DigestService = Depends(get_digest_service),
) -> ApiResponse[GenerateDigestResponse]:
    result = await service.generate(req)
    return ok(request, result)
