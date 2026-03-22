from __future__ import annotations

from dataclasses import dataclass

from app.models.score_investors import (
    InvestorScore,
    InvestorScoreBreakdown,
    ScoreInvestorsRequest,
    ScoreInvestorsResponse,
)
from app.services.confidence import ConfidencePolicy, penalize_for_missing_evidence, to_confidence
from app.services.llm_client import LlmClient


@dataclass(frozen=True)
class ScoreWeights:
    thesis_alignment: float
    stage_fit: float
    check_size_fit: float
    scientific_regulatory_fit: float
    recency: float
    geography: float


def _weighted_overall(*, breakdown: InvestorScoreBreakdown, weights: ScoreWeights) -> int:
    # When scientific_regulatory_fit is null, redistribute its weight to thesis_alignment
    sci_reg = breakdown.scientific_regulatory_fit
    if sci_reg is not None:
        score = (
            breakdown.thesis_alignment * weights.thesis_alignment
            + breakdown.stage_fit * weights.stage_fit
            + breakdown.check_size_fit * weights.check_size_fit
            + sci_reg * weights.scientific_regulatory_fit
            + breakdown.recency * weights.recency
            + breakdown.geography * weights.geography
        )
    else:
        redistributed_thesis = weights.thesis_alignment + weights.scientific_regulatory_fit
        score = (
            breakdown.thesis_alignment * redistributed_thesis
            + breakdown.stage_fit * weights.stage_fit
            + breakdown.check_size_fit * weights.check_size_fit
            + breakdown.recency * weights.recency
            + breakdown.geography * weights.geography
        )
    return int(round(score))


class ScoringService:
    def __init__(self, *, llm: LlmClient, weights: ScoreWeights, confidence_policy: ConfidencePolicy) -> None:
        self._llm = llm
        self._weights = weights
        self._confidence_policy = confidence_policy

    async def score_investors(self, req: ScoreInvestorsRequest) -> ScoreInvestorsResponse:
        results: list[InvestorScore] = []

        for investor in req.investors:
            llm_score = await self._llm.score_investor(
                client_name=req.client.name,
                client_thesis=req.client.thesis,
                client_geography=req.client.geography,
                client_funding_target=req.client.funding_target,
                investor_name=investor.name,
                investor_notes=investor.notes,
            )

            breakdown = InvestorScoreBreakdown(
                thesis_alignment=llm_score.thesis_alignment,
                stage_fit=llm_score.stage_fit,
                check_size_fit=llm_score.check_size_fit,
                scientific_regulatory_fit=llm_score.scientific_regulatory_fit,
                recency=llm_score.recency,
                geography=llm_score.geography,
            )

            overall = _weighted_overall(breakdown=breakdown, weights=self._weights)

            confidence_score = penalize_for_missing_evidence(
                float(llm_score.confidence_score),
                llm_score.evidence_urls,
                policy=self._confidence_policy,
            )

            results.append(
                InvestorScore(
                    investor=investor,
                    overall_score=overall,
                    confidence=to_confidence(confidence_score, policy=self._confidence_policy),
                    evidence_urls=list(llm_score.evidence_urls),
                    breakdown=breakdown,
                    notes=llm_score.notes,
                    outreach_angle=llm_score.outreach_angle,
                    suggested_contact=llm_score.suggested_contact,
                )
            )

        return ScoreInvestorsResponse(results=results)
