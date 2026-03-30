from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import DEFAULT_SCHEMA_VERSION
from app.models.common import Confidence

SignalType = Literal["SEC_EDGAR", "GOOGLE_NEWS", "OTHER", "X_GROK"]


AuthorType = Literal["partner", "firm_handle", "portfolio_founder", "other"]


class XEngagementData(BaseModel):
    replies: int = Field(ge=0)
    reposts: int = Field(ge=0)
    likes: int = Field(ge=0)
    is_original_post: bool
    author: str = Field(max_length=200)
    author_type: AuthorType


class SignalInvestorContext(BaseModel):
    name: str = Field(max_length=200)
    firm: str | None = Field(default=None, max_length=200)
    current_score: int | None = Field(default=None, ge=0, le=100)
    thesis_keywords: list[str] = Field(default_factory=list, max_length=20)
    portfolio_companies: list[str] = Field(default_factory=list, max_length=30)
    key_partners: list[str] = Field(default_factory=list, max_length=10)


class SignalClientContext(BaseModel):
    name: str = Field(max_length=200)
    thesis: str = Field(max_length=1000)
    geography: str | None = Field(default=None, max_length=200)
    modality: str | None = Field(default=None, max_length=200)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    stage: str | None = Field(default=None, max_length=100)


class AnalyzeSignalRequest(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    signal_type: SignalType
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    published_at: str | None = Field(default=None, max_length=64)
    raw_text: str | None = Field(default=None, max_length=20000)
    investor: SignalInvestorContext | None = None
    client: SignalClientContext | None = None
    grok_batch_context: str | None = Field(default=None, max_length=5000)
    x_engagement_data: XEngagementData | None = None


class SignalBriefing(BaseModel):
    headline: str = Field(max_length=300)
    why_it_matters: str = Field(max_length=1000)
    outreach_angle: str = Field(max_length=1000)
    suggested_contact: str = Field(max_length=200)
    time_sensitivity: str = Field(max_length=200)
    source_urls: list[str] = Field(default_factory=list)


class SignalAnalysis(BaseModel):
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    confidence: Confidence
    rationale: str = Field(min_length=1, max_length=4000)
    categories: list[str] = Field(default_factory=list, max_length=20)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)
    relevance_score: int = Field(ge=0, le=100)
    briefing: SignalBriefing
    signal_type: str = Field(max_length=50)
    expires_relevance: str = Field(max_length=32)
    x_signal_type: Literal[
        "thesis_statement", "conference_signal", "fund_activity",
        "portfolio_mention", "hiring_signal", "general_activity",
    ] | None = Field(default=None)


class AnalyzeSignalResponse(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    analysis: SignalAnalysis
