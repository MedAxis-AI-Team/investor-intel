from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import DEFAULT_SCHEMA_VERSION
from app.models.score_investors import PipelineStatus

XSignalType = Literal[
    "thesis_statement", "conference_signal", "fund_activity",
    "portfolio_mention", "hiring_signal", "general_activity",
]

WindowType = Literal["immediate", "this_week", "monitor"]
PriorityType = Literal["high", "medium", "low"]


class DigestClient(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geography: str | None = Field(default=None, max_length=200)
    therapeutic_area: str | None = Field(default=None, max_length=200)
    stage: str | None = Field(default=None, max_length=100)
    target_raise: str | None = Field(default=None, max_length=100)


class DigestSignal(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    summary: str | None = Field(default=None, max_length=4000)


class DigestInvestor(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    pipeline_status: PipelineStatus | None = Field(default=None)


class DigestXSignalInput(BaseModel):
    investor_name: str = Field(min_length=1, max_length=200)
    firm: str = Field(min_length=1, max_length=200)
    signal_summary: str = Field(min_length=1, max_length=1000)
    x_signal_type: str = Field(max_length=50)


class GenerateDigestRequest(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    client: DigestClient
    week_start: str = Field(min_length=1, max_length=32)
    week_end: str = Field(min_length=1, max_length=32)
    signals: list[DigestSignal] = Field(default_factory=list, max_length=200)
    investors: list[DigestInvestor] = Field(default_factory=list, max_length=200)
    market_context: str | None = Field(default=None, max_length=8000)
    x_signals: list[DigestXSignalInput] = Field(default_factory=list, max_length=100)


# ── Client digest models ────────────────────────────────────────────────────

class DigestSection(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    bullets: list[str] = Field(default_factory=list, max_length=50)


class XActivitySignal(BaseModel):
    investor_name: str = Field(min_length=1, max_length=200)
    firm: str = Field(min_length=1, max_length=200)
    signal_summary: str = Field(min_length=1, max_length=1000)
    x_signal_type: XSignalType
    recommended_action: str = Field(max_length=500)
    window: WindowType
    priority: PriorityType


class XActivitySection(BaseModel):
    section_title: str = Field(
        default="X Activity — Investor Signals This Week", max_length=200,
    )
    signals: list[XActivitySignal] = Field(default_factory=list)
    section_note: str | None = Field(default=None, max_length=500)


class DigestPayload(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    preheader: str = Field(min_length=1, max_length=300)
    sections: list[DigestSection] = Field(min_length=1, max_length=20)
    x_activity_section: XActivitySection = Field(default_factory=XActivitySection)


# ── Internal advisor prep models ────────────────────────────────────────────

class AdvisorOutreachAngle(BaseModel):
    investor_name: str
    angle: str = Field(max_length=1000)       # 2-3 sentences: what to lead with
    avoid: str = Field(max_length=500)         # 1 sentence: what NOT to say
    re_engagement_notes: str | None = Field(default=None, max_length=1000)


class AdvisorCallPlan(BaseModel):
    opening_framing: str = Field(max_length=1000)        # ~2 min framing
    discussion_threads: list[str] = Field(min_length=1, max_length=5)
    desired_outcome: str = Field(max_length=500)


class AdvisorObjection(BaseModel):
    objection: str = Field(max_length=500)
    response: str = Field(max_length=1000)


class AdvisorPrepPayload(BaseModel):
    key_insights: list[str] = Field(min_length=1, max_length=5)
    outreach_angles: list[AdvisorOutreachAngle] = Field(default_factory=list, max_length=20)
    call_plan: AdvisorCallPlan
    likely_objections: list[AdvisorObjection] = Field(default_factory=list, max_length=10)
    risks_sensitivities: list[str] = Field(default_factory=list, max_length=10)
    questions_to_ask: list[str] = Field(default_factory=list, max_length=10)


# ── Response ────────────────────────────────────────────────────────────────

class GenerateDigestResponse(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    client_digest: DigestPayload
    internal_digest: AdvisorPrepPayload
