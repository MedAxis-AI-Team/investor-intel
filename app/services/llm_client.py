from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LlmInvestorScore:
    thesis_alignment: int
    stage_fit: int
    check_size_fit: int
    strategic_value: int
    notes: str | None
    evidence_urls: list[str]
    confidence_score: float


@dataclass(frozen=True)
class LlmSignalAnalysis:
    priority: str
    rationale: str
    categories: list[str]
    evidence_urls: list[str]
    confidence_score: float


@dataclass(frozen=True)
class LlmDigestResult:
    subject: str
    preheader: str
    sections: list[tuple[str, list[str]]]


class LlmClient(Protocol):
    async def score_investor(self, *, client_name: str, client_thesis: str, investor_name: str) -> LlmInvestorScore:
        raise NotImplementedError

    async def analyze_signal(self, *, signal_type: str, title: str, url: str, raw_text: str | None) -> LlmSignalAnalysis:
        raise NotImplementedError

    async def generate_digest(
        self, *, client_name: str, week_start: str, week_end: str, signals: list[tuple[str, str]]
    ) -> LlmDigestResult:
        raise NotImplementedError
