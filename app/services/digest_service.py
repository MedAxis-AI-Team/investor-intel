from __future__ import annotations

from app.models.generate_digest import (
    DigestPayload,
    DigestSection,
    GenerateDigestRequest,
    GenerateDigestResponse,
    XActivitySection,
    XActivitySignal,
)
from app.services.llm_client import LlmClient


_WINDOW_ORDER = {"immediate": 0, "this_week": 1, "monitor": 2}


class DigestService:
    def __init__(self, *, llm: LlmClient) -> None:
        self._llm = llm

    async def generate(self, req: GenerateDigestRequest) -> GenerateDigestResponse:
        x_signal_dicts: list[dict] | None = None
        if req.x_signals:
            x_signal_dicts = [s.model_dump() for s in req.x_signals]

        llm_result = await self._llm.generate_digest(
            client_name=req.client.name,
            week_start=req.week_start,
            week_end=req.week_end,
            signals=[(s.title, s.url) for s in req.signals],
            investors=[(inv.name, inv.pipeline_status) for inv in req.investors],
            market_context=req.market_context,
            x_signals=x_signal_dicts,
        )

        sections = [DigestSection(title=title, bullets=bullets) for (title, bullets) in llm_result.sections]

        x_activity_signals = [
            XActivitySignal(
                investor_name=sig.investor_name,
                firm=sig.firm,
                signal_summary=sig.signal_summary,
                x_signal_type=sig.x_signal_type,
                recommended_action=sig.recommended_action,
                window=sig.window,
                priority=sig.priority,
            )
            for sig in llm_result.x_activity_section.signals
        ]
        x_activity_signals.sort(key=lambda s: _WINDOW_ORDER.get(s.window, 99))

        x_activity_section = XActivitySection(
            signals=x_activity_signals,
            section_note=llm_result.x_activity_section.section_note,
        )

        payload = DigestPayload(
            subject=llm_result.subject,
            preheader=llm_result.preheader,
            sections=sections,
            x_activity_section=x_activity_section,
        )
        return GenerateDigestResponse(payload=payload)
