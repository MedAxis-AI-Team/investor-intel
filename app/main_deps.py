from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.services.anthropic_client import AnthropicLlmClient
from app.services.confidence import ConfidencePolicy
from app.services.digest_service import DigestService
from app.services.grant_scoring_service import GrantScoringService
from app.services.ingest_service import IngestService
from app.services.scoring_service import ScoringService, ScoreWeights
from app.services.signal_service import SignalService
from app.services.llm_client import LlmClient


def get_llm_client(settings: Settings = Depends(get_settings)) -> LlmClient:
    return AnthropicLlmClient(settings=settings)

def get_confidence_policy(settings: Settings = Depends(get_settings)) -> ConfidencePolicy:
    return ConfidencePolicy(
        high_threshold=float(settings.confidence_high_threshold),
        medium_threshold=float(settings.confidence_medium_threshold),
        missing_evidence_penalty=float(settings.evidence_missing_penalty),
    )


def get_score_weights(settings: Settings = Depends(get_settings)) -> ScoreWeights:
    return ScoreWeights(
        thesis_alignment=float(settings.score_weight_thesis_alignment),
        stage_fit=float(settings.score_weight_stage_fit),
        check_size_fit=float(settings.score_weight_check_size_fit),
        scientific_regulatory_fit=float(settings.score_weight_scientific_regulatory_fit),
        recency=float(settings.score_weight_recency),
        geography=float(settings.score_weight_geography),
    )

def get_scoring_service(
    llm: LlmClient = Depends(get_llm_client),
    weights: ScoreWeights = Depends(get_score_weights),
    confidence_policy: ConfidencePolicy = Depends(get_confidence_policy),
) -> ScoringService:
    return ScoringService(llm=llm, weights=weights, confidence_policy=confidence_policy)


def get_signal_service(
    llm: LlmClient = Depends(get_llm_client),
    confidence_policy: ConfidencePolicy = Depends(get_confidence_policy),
) -> SignalService:
    return SignalService(llm=llm, confidence_policy=confidence_policy)


def get_digest_service(llm: LlmClient = Depends(get_llm_client)) -> DigestService:
    return DigestService(llm=llm)


def get_grant_scoring_service(llm: LlmClient = Depends(get_llm_client)) -> GrantScoringService:
    return GrantScoringService(llm=llm)


def get_db_pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="database_unavailable")
    return pool


def get_ingest_service(pool: asyncpg.Pool = Depends(get_db_pool)) -> IngestService:
    return IngestService(pool=pool)


def get_optional_ingest_service(request: Request) -> IngestService | None:
    """Return IngestService when pool is available, None otherwise (non-blocking degraded mode)."""
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        return None
    return IngestService(pool=pool)
