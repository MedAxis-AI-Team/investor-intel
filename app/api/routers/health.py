from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    pool = getattr(request.app.state, "db_pool", None)
    db_status = "ok" if (pool is not None and not pool.is_closing()) else "unavailable"
    return {"status": "ok", "version": __version__, "db": db_status}
