from __future__ import annotations

from app.models.analyze_signal import (
    AnalyzeSignalRequest,
    AnalyzeSignalResponse,
    SignalAnalysis,
    SignalBriefing,
)
from app.services._field_limits import (
    SIGNAL_CONTACT_MAX,
    SIGNAL_HEADLINE_MAX,
    SIGNAL_OUTREACH_MAX,
    SIGNAL_RATIONALE_MAX,
    SIGNAL_TIMESENS_MAX,
    SIGNAL_WHY_MAX,
)
from app.services.confidence import ConfidencePolicy, penalize_for_missing_evidence, to_confidence
from app.services.llm_client import LlmClient


def _trunc(value: object, limit: int, default: str = "") -> str:
    s = "" if value is None else str(value)
    return s[:limit] if len(s) > limit else s


class SignalService:
    def __init__(self, *, llm: LlmClient, confidence_policy: ConfidencePolicy) -> None:
        self._llm = llm
        self._confidence_policy = confidence_policy

    async def analyze(self, req: AnalyzeSignalRequest) -> AnalyzeSignalResponse:
        eng = req.x_engagement_data
        llm_result = await self._llm.analyze_signal(
            signal_type=req.signal_type,
            title=req.title,
            url=req.url,
            published_at=req.published_at,
            raw_text=req.raw_text,
            investor_name=req.investor.name if req.investor else None,
            investor_firm=req.investor.firm if req.investor else None,
            investor_thesis_keywords=req.investor.thesis_keywords if req.investor else None,
            investor_portfolio_companies=req.investor.portfolio_companies if req.investor else None,
            investor_key_partners=req.investor.key_partners if req.investor else None,
            client_name=req.client.name if req.client else None,
            client_thesis=req.client.thesis if req.client else None,
            client_geography=req.client.geography if req.client else None,
            client_modality=req.client.modality if req.client else None,
            client_keywords=req.client.keywords if req.client else None,
            client_stage=req.client.stage if req.client else None,
            grok_batch_context=req.grok_batch_context,
            x_engagement_replies=eng.replies if eng else None,
            x_engagement_reposts=eng.reposts if eng else None,
            x_engagement_likes=eng.likes if eng else None,
            x_engagement_is_original=eng.is_original_post if eng else None,
            x_engagement_author=eng.author if eng else None,
            x_engagement_author_type=eng.author_type if eng else None,
        )

        confidence_score = penalize_for_missing_evidence(
            float(llm_result.confidence_score),
            llm_result.evidence_urls,
            policy=self._confidence_policy,
        )

        briefing = SignalBriefing(
            headline=_trunc(llm_result.briefing.headline, SIGNAL_HEADLINE_MAX),
            why_it_matters=_trunc(llm_result.briefing.why_it_matters, SIGNAL_WHY_MAX),
            outreach_angle=_trunc(llm_result.briefing.outreach_angle, SIGNAL_OUTREACH_MAX),
            suggested_contact=_trunc(llm_result.briefing.suggested_contact, SIGNAL_CONTACT_MAX),
            time_sensitivity=_trunc(llm_result.briefing.time_sensitivity, SIGNAL_TIMESENS_MAX),
            source_urls=list(llm_result.briefing.source_urls),
        )

        analysis = SignalAnalysis(
            priority=str(llm_result.priority),
            confidence=to_confidence(confidence_score, policy=self._confidence_policy),
            rationale=_trunc(llm_result.rationale, SIGNAL_RATIONALE_MAX),
            categories=list(llm_result.categories),
            evidence_urls=list(llm_result.evidence_urls),
            relevance_score=llm_result.relevance_score,
            briefing=briefing,
            signal_type=llm_result.signal_type,
            expires_relevance=llm_result.expires_relevance,
            x_signal_type=llm_result.x_signal_type if req.signal_type == "X_GROK" else None,
        )

        return AnalyzeSignalResponse(analysis=analysis)
