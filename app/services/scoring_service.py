from __future__ import annotations

from dataclasses import dataclass

from app.models.score_investors import (
    DimensionStrengths,
    InvestorAdvisorScore,
    InvestorInteractionBrief,
    InvestorScore,
    InvestorScoreBreakdown,
    ScoreInvestorsRequest,
    ScoreInvestorsResponse,
)
from app.services._llm_normalizers import bucket_score, compute_investor_tier
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

    async def score_investors(
        self,
        req: ScoreInvestorsRequest,
        *,
        investor_sources: list[str] | None = None,
        investor_interactions: list[list[InvestorInteractionBrief]] | None = None,
    ) -> ScoreInvestorsResponse:
        """Score investors and return parallel client-facing and advisor-internal DTOs.

        investor_sources: parallel to req.investors — "discovery" or "client_provided".
                          Defaults to all "discovery" when omitted.
        investor_interactions: parallel to req.investors — interaction history from client tracker.
                               Defaults to empty lists when omitted.
        """
        results: list[InvestorScore] = []
        advisor_data: list[InvestorAdvisorScore] = []

        for idx, investor in enumerate(req.investors):
            source: str = (investor_sources[idx] if investor_sources else None) or "discovery"
            interactions: list[InvestorInteractionBrief] = (
                investor_interactions[idx] if investor_interactions else []
            ) or []

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

            composite_score = _weighted_overall(breakdown=breakdown, weights=self._weights)

            confidence_score = penalize_for_missing_evidence(
                float(llm_score.confidence_score),
                llm_score.evidence_urls,
                policy=self._confidence_policy,
            )

            sci_depth = bucket_score(breakdown.scientific_regulatory_fit)
            dimension_strengths = DimensionStrengths(
                strategic_fit=bucket_score(breakdown.thesis_alignment) or "Low",
                stage_relevance=bucket_score(breakdown.stage_fit) or "Low",
                capital_alignment=bucket_score(breakdown.check_size_fit) or "Low",
                scientific_depth=sci_depth,
                market_activity=bucket_score(breakdown.recency) or "Low",
                geographic_proximity=bucket_score(breakdown.geography) or "Low",
            )

            results.append(InvestorScore(
                investor=investor,
                composite_score=composite_score,
                investor_tier=compute_investor_tier(composite_score),
                investor_source=source,
                confidence=to_confidence(confidence_score, policy=self._confidence_policy),
                suggested_contact=llm_score.suggested_contact,
                evidence_urls=list(llm_score.evidence_urls),
                dimension_strengths=dimension_strengths,
                narrative_summary=llm_score.narrative_summary,
                top_claims=list(llm_score.top_claims),
                interactions=interactions,
            ))

            advisor_data.append(InvestorAdvisorScore(
                investor_name=investor.name,
                outreach_angle=llm_score.outreach_angle,
                avoid=llm_score.avoid,
                re_engagement_notes=None,
                full_axis_breakdown=breakdown,
                notes=llm_score.notes,
                evidence_urls=list(llm_score.evidence_urls),
            ))

        return ScoreInvestorsResponse(results=results, advisor_data=advisor_data)
