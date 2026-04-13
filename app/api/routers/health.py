from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__
from app.services.scoring_config import _CLASSIFIER_VERSION

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    summary="Service health check",
    description=(
        "Returns service status, API version, scoring classifier version, "
        "and database connectivity. `db: unavailable` means `SUPABASE_CONNECTION_STRING` "
        "is not set or the pool is closing — ingestion endpoints will return 503."
    ),
)
async def health(request: Request) -> dict[str, str]:
    pool = getattr(request.app.state, "db_pool", None)
    db_status = "ok" if (pool is not None and not pool.is_closing()) else "unavailable"
    return {
        "status": "ok",
        "version": __version__,
        "scoring_classifier": _CLASSIFIER_VERSION,
        "db": db_status,
    }
