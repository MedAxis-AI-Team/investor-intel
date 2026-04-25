from __future__ import annotations

from app.models.generate_digest import (
    AdvisorCallPlan,
    AdvisorObjection,
    AdvisorOutreachAngle,
    AdvisorPrepPayload,
    DigestPayload,
    DigestSection,
    GenerateDigestRequest,
    GenerateDigestResponse,
    XActivitySection,
    XActivitySignal,
)
from app.services._field_limits import (
    ADVISOR_ANGLE_MAX,
    ADVISOR_AVOID_MAX,
    ADVISOR_DESIRED_OUTCOME_MAX,
    ADVISOR_OBJECTION_MAX,
    ADVISOR_OPENING_MAX,
    ADVISOR_REENGAGEMENT_MAX,
    ADVISOR_RESPONSE_MAX,
    DIGEST_BULLET_MAX,
    DIGEST_PREHEADER_MAX,
    DIGEST_RECOMMENDED_ACTION_MAX,
    DIGEST_SIGNAL_SUMMARY_MAX,
    DIGEST_SUBJECT_MAX,
    DIGEST_TITLE_MAX,
)
from app.services.llm_client import LlmAdvisorPrep, LlmClient


def _trunc(value: object, limit: int, default: str = "") -> str:
    s = "" if value is None else str(value)
    return s[:limit] if len(s) > limit else s


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
            therapeutic_area=req.client.therapeutic_area,
            stage=req.client.stage,
            target_raise=req.client.target_raise,
        )

        # Filter sections with empty titles; DigestSection requires min_length=1 on title.
        # DigestPayload requires at least 1 section, so fall back to a placeholder if all are empty.
        sections = [
            DigestSection(
                title=_trunc(title, DIGEST_TITLE_MAX),
                bullets=[_trunc(b, DIGEST_BULLET_MAX) for b in bullets],
            )
            for (title, bullets) in llm_result.sections
            if title
        ]
        if not sections:
            sections = [DigestSection(title="Weekly Summary", bullets=[])]

        x_activity_signals = [
            XActivitySignal(
                investor_name=sig.investor_name,
                firm=sig.firm,
                signal_summary=_trunc(sig.signal_summary, DIGEST_SIGNAL_SUMMARY_MAX),
                x_signal_type=sig.x_signal_type,
                recommended_action=_trunc(sig.recommended_action, DIGEST_RECOMMENDED_ACTION_MAX),
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

        client_digest = DigestPayload(
            subject=_trunc(llm_result.subject, DIGEST_SUBJECT_MAX),
            preheader=_trunc(llm_result.preheader, DIGEST_PREHEADER_MAX),
            sections=sections,
            x_activity_section=x_activity_section,
        )

        internal_digest = self._build_advisor_payload(llm_result.advisor_prep)

        return GenerateDigestResponse(client_digest=client_digest, internal_digest=internal_digest)

    def _build_advisor_payload(self, prep: LlmAdvisorPrep) -> AdvisorPrepPayload:
        outreach_angles = [
            AdvisorOutreachAngle(
                investor_name=a.investor_name,
                angle=_trunc(a.angle, ADVISOR_ANGLE_MAX),
                avoid=_trunc(a.avoid, ADVISOR_AVOID_MAX),
                re_engagement_notes=(
                    _trunc(a.re_engagement_notes, ADVISOR_REENGAGEMENT_MAX)
                    if a.re_engagement_notes is not None else None
                ),
            )
            for a in prep.outreach_angles
        ]

        # discussion_threads requires min_length=1; guard against empty LLM output.
        discussion_threads = list(prep.call_plan.discussion_threads) or ["Review investor thesis alignment"]
        call_plan = AdvisorCallPlan(
            opening_framing=_trunc(prep.call_plan.opening_framing, ADVISOR_OPENING_MAX),
            discussion_threads=discussion_threads,
            desired_outcome=_trunc(prep.call_plan.desired_outcome, ADVISOR_DESIRED_OUTCOME_MAX),
        )

        objections = [
            AdvisorObjection(
                objection=_trunc(o.objection, ADVISOR_OBJECTION_MAX),
                response=_trunc(o.response, ADVISOR_RESPONSE_MAX),
            )
            for o in prep.likely_objections
        ]

        # key_insights requires min_length=1; guard against empty LLM output.
        key_insights = list(prep.key_insights) or ["Review this week's signals for investor outreach opportunities"]
        return AdvisorPrepPayload(
            key_insights=key_insights,
            outreach_angles=outreach_angles,
            call_plan=call_plan,
            likely_objections=objections,
            risks_sensitivities=list(prep.risks_sensitivities),
            questions_to_ask=list(prep.questions_to_ask),
        )
