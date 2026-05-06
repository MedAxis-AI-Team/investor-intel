from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app import __version__ as _APP_VERSION
from app.config import get_settings
from app.models.common import Confidence
from app.models.score_investors import (
    DimensionStrengths,
    InvestorAdvisorScore,
    InvestorInput,
    InvestorInteractionBrief,
    InvestorScore,
    InvestorScoreBreakdown,
    ScoreInvestorsRequest,
    ScoreInvestorsResponse,
    ScoringPolicy,
    VersionBundle,
)
from app.services._field_limits import AVOID_MAX, EVIDENCE_URLS_MAX, NARRATIVE_MAX, NOTES_MAX, OUTREACH_MAX, TOP_CLAIMS_MAX
from app.services._llm_normalizers import bucket_score, compute_investor_tier
from app.services.confidence import ConfidencePolicy, penalize_for_missing_evidence, to_confidence
from app.services.llm_client import LlmClient
from app.services.scoring_config import ScoringInstructions, _CLASSIFIER_VERSION, build_scoring_instructions

if TYPE_CHECKING:
    from app.services.ingest_service import ClientInvestorRecord

_log = logging.getLogger(__name__)
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")


def _normalize_firm_name(name: str) -> str:
    return _NON_ALNUM.sub("", name.lower()).strip()


def _grant_stub(
    investor: InvestorInput,
    source: str,
    interactions: list[InvestorInteractionBrief],
) -> tuple[InvestorScore, InvestorAdvisorScore]:
    """Return a zero-score stub for grant-type investors.

    Grant organizations are not evaluated by the VC scoring pipeline.
    They are preserved in the response so callers can route them to /score-grants.
    """
    result = InvestorScore(
        investor=investor,
        composite_score=0,
        investor_tier="Below Threshold",
        investor_source=source,
        confidence=Confidence(score=0.0, tier="LOW"),
        suggested_contact="Not identified",
        evidence_urls=[],
        dimension_strengths=DimensionStrengths(
            strategic_fit="Low",
            stage_relevance="Low",
            capital_alignment="Low",
            scientific_depth=None,
            market_activity="Low",
            geographic_proximity="Low",
        ),
        narrative_summary="Grant-type organization. VC scoring does not apply. Evaluate via /score-grants.",
        top_claims=[],
        interactions=interactions,
    )
    advisor = InvestorAdvisorScore(
        investor_name=investor.name,
        outreach_angle="",
        avoid=None,
        re_engagement_notes=None,
        full_axis_breakdown=InvestorScoreBreakdown(
            thesis_alignment=0,
            stage_fit=0,
            check_size_fit=0,
            scientific_regulatory_fit=None,
            recency=0,
            geography=0,
        ),
        notes="[GRANT] Excluded from VC scoring pipeline. Route to /score-grants for grant evaluation.",
        evidence_urls=[],
    )
    return result, advisor


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


def _investor_text(investor: InvestorInput) -> str:
    return f"{investor.name} {investor.notes or ''} {investor.investor_type or ''}".lower()


def _matches(term: str, investor: InvestorInput) -> bool:
    return term.lower() in _investor_text(investor)


def _hard_excluded(policy: ScoringPolicy, investor: InvestorInput) -> bool:
    if not policy.hard_exclusions:
        return False
    return any(_matches(exc.match_term, investor) for exc in policy.hard_exclusions)


def _policy_weighted_overall(
    *,
    breakdown: InvestorScoreBreakdown,
    policy: ScoringPolicy,
    investor: InvestorInput,
) -> int:
    axis_map: dict[str, float] = {
        "thesis_alignment": float(breakdown.thesis_alignment),
        "stage_fit": float(breakdown.stage_fit),
        "check_size_fit": float(breakdown.check_size_fit),
        "scientific_regulatory_fit": float(breakdown.scientific_regulatory_fit or 0),
        "recency": float(breakdown.recency),
        "geography": float(breakdown.geography),
    }

    weight_sum = sum(c.weight for c in policy.policy_components)
    if abs(weight_sum - 1.0) > 0.01:
        _log.info("policy_components weights sum %.4f; normalizing to 1.0", weight_sum)

    score = 0.0
    for comp in policy.policy_components:
        raw = axis_map[comp.axis]
        for boost in comp.soft_boosts:
            if _matches(boost.term, investor):
                raw = min(100.0, raw * boost.multiplier)
        score += (comp.weight / weight_sum) * raw

    if policy.capital_channels:
        for ch in policy.capital_channels:
            if _matches(ch.match_term, investor):
                score = min(100.0, max(0.0, score * ch.multiplier))

    return int(round(score))


def _policy_to_instructions(policy: ScoringPolicy) -> ScoringInstructions:
    guidance_parts = [
        f"{c.axis}: {c.guidance}" for c in policy.policy_components if c.guidance
    ]
    return ScoringInstructions(
        profile_type="custom_policy",
        thesis_keywords=[],
        investor_universe_hints="Custom scoring policy — see component guidance.",
        stage_fit_guidance="Custom scoring policy — see component guidance.",
        sci_reg_guidance="Custom scoring policy — see component guidance.",
        score_scientific_regulatory=True,
        modifier_keywords=[],
        modifier_guidance="\n".join(guidance_parts),
        classifier_version=_CLASSIFIER_VERSION,
    )


def _parse_scoring_policy(raw: dict) -> ScoringPolicy | None:
    """Parse raw dict to ScoringPolicy. Logs and returns None on validation failure."""
    try:
        return ScoringPolicy.model_validate(raw)
    except ValidationError as exc:
        _log.warning(
            "scoring_policy validation failed — falling back to client_profile path: %s | payload=%r",
            exc,
            raw,
        )
        return None


def _build_version_bundle(policy: ScoringPolicy | None, *, raw_policy: dict | None) -> VersionBundle:
    if policy is not None:
        spv = policy.version
    elif raw_policy is not None:
        spv = "fallback"
    else:
        spv = "none"
    return VersionBundle(
        scoring_policy_version=spv,
        endpoint_version=_APP_VERSION,
        prompt_version=_CLASSIFIER_VERSION,
        model_version=get_settings().llm_model,
    )


class ScoringService:
    def __init__(self, *, llm: LlmClient, weights: ScoreWeights, confidence_policy: ConfidencePolicy) -> None:
        self._llm = llm
        self._weights = weights
        self._confidence_policy = confidence_policy

    @staticmethod
    def resolve_investor_context(
        investors: list[InvestorInput],
        client_records: list[ClientInvestorRecord],
    ) -> tuple[list[str], list[list[InvestorInteractionBrief]]]:
        """Match investors to client tracker records by normalized firm name.

        Returns parallel (sources, interactions) lists aligned to the investors list.
        source = "client_provided" if matched in tracker, "discovery" if not.
        """
        client_map = {_normalize_firm_name(r.firm_name): r for r in client_records}
        sources: list[str] = []
        interactions: list[list[InvestorInteractionBrief]] = []
        for investor in investors:
            record = client_map.get(_normalize_firm_name(investor.name))
            if record:
                sources.append("client_provided")
                interactions.append(list(record.interactions))
            else:
                sources.append("discovery")
                interactions.append([])
        return sources, interactions

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
        policy = _parse_scoring_policy(req.scoring_policy) if req.scoring_policy is not None else None
        version_bundle = _build_version_bundle(policy, raw_policy=req.scoring_policy)
        _log.info("version_bundle: %r", version_bundle.model_dump())

        if policy is not None:
            scoring_instructions = _policy_to_instructions(policy)
        else:
            scoring_instructions = build_scoring_instructions(
                req.client.client_profile,
                list(req.client.modifiers),
            )

        results: list[InvestorScore] = []
        advisor_data: list[InvestorAdvisorScore] = []

        for idx, investor in enumerate(req.investors):
            source: str = (investor_sources[idx] if investor_sources else None) or "discovery"
            interactions: list[InvestorInteractionBrief] = (
                investor_interactions[idx] if investor_interactions else []
            ) or []

            if investor.investor_type == "grant":
                result, advisor = _grant_stub(investor, source, interactions)
                results.append(result)
                advisor_data.append(advisor)
                continue

            llm_score = await self._llm.score_investor(
                client_name=req.client.name,
                client_thesis=req.client.thesis,
                client_geography=req.client.geography,
                client_funding_target=req.client.funding_target,
                investor_name=investor.name,
                investor_notes=investor.notes,
                scoring_instructions=scoring_instructions,
            )

            breakdown = InvestorScoreBreakdown(
                thesis_alignment=llm_score.thesis_alignment,
                stage_fit=llm_score.stage_fit,
                check_size_fit=llm_score.check_size_fit,
                scientific_regulatory_fit=llm_score.scientific_regulatory_fit,
                recency=llm_score.recency,
                geography=llm_score.geography,
            )

            if policy is not None:
                if _hard_excluded(policy, investor):
                    composite_score = 0
                else:
                    composite_score = _policy_weighted_overall(
                        breakdown=breakdown,
                        policy=policy,
                        investor=investor,
                    )
            else:
                composite_score = _weighted_overall(breakdown=breakdown, weights=self._weights)

            confidence_score = penalize_for_missing_evidence(
                float(llm_score.confidence_score),
                llm_score.evidence_urls,
                policy=self._confidence_policy,
            )

            # Angel investors have limited public data — cap confidence at MEDIUM
            if investor.investor_type == "angel" and confidence_score >= self._confidence_policy.high_threshold:
                confidence_score = self._confidence_policy.high_threshold - 0.001

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
                evidence_urls=list(llm_score.evidence_urls)[:EVIDENCE_URLS_MAX],
                dimension_strengths=dimension_strengths,
                narrative_summary=(llm_score.narrative_summary or "")[:NARRATIVE_MAX],
                top_claims=list(llm_score.top_claims)[:TOP_CLAIMS_MAX],
                interactions=interactions,
            ))

            advisor_notes = llm_score.notes
            if investor.investor_type == "angel":
                angel_flag = "[ANGEL] Limited public data — confidence capped at MEDIUM. Manual verification recommended."
                advisor_notes = f"{advisor_notes}\n\n{angel_flag}" if advisor_notes else angel_flag
            if advisor_notes and len(advisor_notes) > NOTES_MAX:
                advisor_notes = advisor_notes[:NOTES_MAX]

            advisor_data.append(InvestorAdvisorScore(
                investor_name=investor.name,
                outreach_angle=(llm_score.outreach_angle or "")[:OUTREACH_MAX],
                avoid=(llm_score.avoid[:AVOID_MAX] if llm_score.avoid else None),
                re_engagement_notes=None,
                full_axis_breakdown=breakdown,
                notes=advisor_notes,
                evidence_urls=list(llm_score.evidence_urls)[:EVIDENCE_URLS_MAX],
            ))

        return ScoreInvestorsResponse(results=results, advisor_data=advisor_data, version_bundle=version_bundle)
