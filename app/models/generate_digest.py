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
        default="X Activity \u2014 Investor Signals This Week", max_length=200,
    )
    signals: list[XActivitySignal] = Field(default_factory=list)
    section_note: str | None = Field(default=None, max_length=500)


class DigestPayload(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    preheader: str = Field(min_length=1, max_length=300)
    sections: list[DigestSection] = Field(min_length=1, max_length=20)
    x_activity_section: XActivitySection = Field(default_factory=XActivitySection)


class GenerateDigestResponse(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    payload: DigestPayload
