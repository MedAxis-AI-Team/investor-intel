from __future__ import annotations

from app.models.analyze_signal import AnalyzeSignalRequest, AnalyzeSignalResponse, SignalAnalysis
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
            raw_text=req.raw_text,
        )

        confidence_score = penalize_for_missing_evidence(
            float(llm_result.confidence_score),
            llm_result.evidence_urls,
            policy=self._confidence_policy,
        )

        analysis = SignalAnalysis(
            priority=str(llm_result.priority),
            confidence=to_confidence(confidence_score, policy=self._confidence_policy),
            rationale=str(llm_result.rationale),
            categories=list(llm_result.categories),
            evidence_urls=list(llm_result.evidence_urls),
        )

        return AnalyzeSignalResponse(analysis=analysis)
