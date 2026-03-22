from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.services.llm_client import LlmInvestorScore


Severity = Literal["CRITICAL", "WARNING", "INFO"]


@dataclass(frozen=True)
class ValidationResult:
    validator_name: str
    passed: bool
    severity: Severity
    message: str
    details: dict | None = None


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    name: str
    client_name: str
    client_thesis: str
    client_geography: str | None
    client_funding_target: str | None
    investor_name: str
    investor_notes: str | None
    expected_tier: str | None = None
    expected_ranges: dict[str, list[int]] = field(default_factory=dict)
    scientific_regulatory_fit_applicable: bool = True


class Validator(Protocol):
    async def validate(
        self, score: LlmInvestorScore, test_case: BenchmarkCase
    ) -> list[ValidationResult]: ...
