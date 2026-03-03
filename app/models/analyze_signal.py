from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import DEFAULT_SCHEMA_VERSION
from app.models.common import Confidence

SignalType = Literal["SEC_EDGAR", "GOOGLE_NEWS", "OTHER"]


class AnalyzeSignalRequest(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    signal_type: SignalType
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    published_at: str | None = Field(default=None, max_length=64)
    raw_text: str | None = Field(default=None, max_length=20000)


class SignalAnalysis(BaseModel):
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    confidence: Confidence
    rationale: str = Field(min_length=1, max_length=4000)
    categories: list[str] = Field(default_factory=list, max_length=20)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)


class AnalyzeSignalResponse(BaseModel):
    schema_version: str = Field(default=DEFAULT_SCHEMA_VERSION, max_length=32)
    analysis: SignalAnalysis
