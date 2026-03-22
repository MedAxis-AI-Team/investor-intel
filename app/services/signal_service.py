from __future__ import annotations

from app.models.analyze_signal import (
    AnalyzeSignalRequest,
    AnalyzeSignalResponse,
    SignalAnalysis,
    SignalBriefing,
)
from app.services.confidence import ConfidencePolicy, penalize_for_missing_evidence, to_confidence
from app.services.llm_client import LlmClient


class SignalService:
    def __init__(self, *, llm: LlmClient, confidence_policy: ConfidencePolicy) -> None:
        self._llm = llm
        self._confidence_policy = confidence_policy

    async def analyze(self, req: AnalyzeSignalRequest) -> AnalyzeSignalResponse:
        llm_result = await self._llm.analyze_signal(
            signal_type=req.signal_type,
            title=req.title,
            url=req.url,
            published_at=req.published_at,
            raw_text=req.raw_text,
            investor_name=req.investor.name if req.investor else None,
            investor_thesis_keywords=req.investor.thesis_keywords if req.investor else None,
            investor_portfolio_companies=req.investor.portfolio_companies if req.investor else None,
            investor_key_partners=req.investor.key_partners if req.investor else None,
            client_name=req.client.name if req.client else None,
            client_thesis=req.client.thesis if req.client else None,
            client_geography=req.client.geography if req.client else None,
        )

        confidence_score = penalize_for_missing_evidence(
            float(llm_result.confidence_score),
            llm_result.evidence_urls,
            policy=self._confidence_policy,
        )

        briefing = SignalBriefing(
            headline=llm_result.briefing.headline,
            why_it_matters=llm_result.briefing.why_it_matters,
            outreach_angle=llm_result.briefing.outreach_angle,
            suggested_contact=llm_result.briefing.suggested_contact,
            time_sensitivity=llm_result.briefing.time_sensitivity,
            source_urls=list(llm_result.briefing.source_urls),
        )

        analysis = SignalAnalysis(
            priority=str(llm_result.priority),
            confidence=to_confidence(confidence_score, policy=self._confidence_policy),
            rationale=str(llm_result.rationale),
            categories=list(llm_result.categories),
            evidence_urls=list(llm_result.evidence_urls),
            relevance_score=llm_result.relevance_score,
            briefing=briefing,
            signal_type=llm_result.signal_type,
            expires_relevance=llm_result.expires_relevance,
        )

        return AnalyzeSignalResponse(analysis=analysis)
