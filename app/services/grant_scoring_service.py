from __future__ import annotations

from datetime import date

from app.models.score_grants import (
    GrantScoreBreakdown,
    ScoreGrantsRequest,
    ScoreGrantsResponse,
    ScoredGrant,
)
from app.services._field_limits import GRANT_GUIDANCE_MAX, GRANT_RATIONALE_MAX
from app.services._llm_normalizers import normalize_grant_confidence
from app.services.llm_client import LlmClient


def _trunc(value: object, limit: int, default: str = "") -> str:
    s = "" if value is None else str(value)
    return s[:limit] if len(s) > limit else s


def _days_until_deadline(deadline_str: str | None) -> int | None:
    if not deadline_str:
        return None
    try:
        deadline = date.fromisoformat(deadline_str)
        return (deadline - date.today()).days
    except ValueError:
        return None


class GrantScoringService:
    def __init__(self, *, llm: LlmClient) -> None:
        self._llm = llm

    async def score_grants(self, req: ScoreGrantsRequest) -> ScoreGrantsResponse:
        scored: list[ScoredGrant] = []

        for grant in req.grants:
            llm_score = await self._llm.score_grant(
                company_name=req.client_profile.company_name,
                therapeutic_area=req.client_profile.therapeutic_area,
                stage=req.client_profile.stage,
                fda_pathway=req.client_profile.fda_pathway,
                keywords=req.client_profile.keywords,
                grant_title=grant.title,
                grant_agency=grant.agency,
                grant_program=grant.program,
                grant_description=grant.description,
                grant_eligibility=grant.eligibility,
                grant_award_amount=grant.award_amount,
                grant_deadline=grant.deadline,
            )

            breakdown = GrantScoreBreakdown(
                therapeutic_match=llm_score.therapeutic_match,
                stage_eligibility=llm_score.stage_eligibility,
                award_size_relevance=llm_score.award_size_relevance,
                deadline_feasibility=llm_score.deadline_feasibility,
                historical_funding=llm_score.historical_funding,
            )

            scored.append(
                ScoredGrant(
                    title=grant.title,
                    source=grant.source,
                    agency=grant.agency,
                    program=grant.program,
                    award_amount=grant.award_amount,
                    deadline=grant.deadline,
                    days_until_deadline=_days_until_deadline(grant.deadline),
                    url=grant.url,
                    overall_score=llm_score.overall_score,
                    breakdown=breakdown,
                    rationale=_trunc(llm_score.rationale, GRANT_RATIONALE_MAX),
                    application_guidance=(
                        _trunc(llm_score.application_guidance, GRANT_GUIDANCE_MAX)
                        if llm_score.application_guidance is not None else None
                    ),
                    confidence=normalize_grant_confidence(llm_score.confidence),
                )
            )

        scored.sort(key=lambda g: g.overall_score, reverse=True)

        high_count = sum(1 for g in scored if g.overall_score >= 75)
        summary = (
            f"{high_count} high-relevance grant opportunit{'y' if high_count == 1 else 'ies'} identified "
            f"out of {len(scored)} evaluated."
        )

        return ScoreGrantsResponse(
            scored_grants=scored,
            summary=summary,
        )
