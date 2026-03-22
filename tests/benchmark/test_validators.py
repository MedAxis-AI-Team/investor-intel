from __future__ import annotations

import pytest

from app.services.llm_client import LlmInvestorScore

from benchmarks.validators.base import BenchmarkCase
from benchmarks.validators.field_validators import ComputationValidator, FieldValidator
from benchmarks.validators.url_validators import UrlValidator


def _make_score(**overrides: object) -> LlmInvestorScore:
    defaults = {
        "thesis_alignment": 80,
        "stage_fit": 75,
        "check_size_fit": 70,
        "scientific_regulatory_fit": 65,
        "recency": 60,
        "geography": 85,
        "notes": "Good fit",
        "outreach_angle": "Discuss CAR-T portfolio synergies",
        "suggested_contact": "John Doe, Partner",
        "evidence_urls": ["https://example.com/report"],
        "confidence_score": 0.85,
    }
    defaults.update(overrides)
    return LlmInvestorScore(**defaults)


def _make_case(**overrides: object) -> BenchmarkCase:
    defaults = {
        "id": "test_001",
        "name": "Test case",
        "client_name": "TestCo",
        "client_thesis": "Testing",
        "client_geography": "US",
        "client_funding_target": "$5M Seed",
        "investor_name": "TestVC",
        "investor_notes": "VC",
        "expected_tier": "HIGH",
        "expected_ranges": {},
        "scientific_regulatory_fit_applicable": True,
    }
    defaults.update(overrides)
    return BenchmarkCase(**defaults)


# --- FieldValidator ---

@pytest.mark.asyncio
async def test_field_validator_all_valid() -> None:
    score = _make_score()
    case = _make_case()
    validator = FieldValidator()
    results = await validator.validate(score, case)
    assert all(r.passed for r in results)


@pytest.mark.asyncio
async def test_field_validator_score_out_of_range() -> None:
    score = _make_score(thesis_alignment=150)
    validator = FieldValidator()
    results = await validator.validate(score, _make_case())
    failures = [r for r in results if not r.passed and r.severity == "CRITICAL"]
    assert any("thesis_alignment=150" in r.message for r in failures)


@pytest.mark.asyncio
async def test_field_validator_negative_score() -> None:
    score = _make_score(stage_fit=-5)
    validator = FieldValidator()
    results = await validator.validate(score, _make_case())
    failures = [r for r in results if not r.passed and r.severity == "CRITICAL"]
    assert any("stage_fit=-5" in r.message for r in failures)


@pytest.mark.asyncio
async def test_field_validator_confidence_out_of_range() -> None:
    score = _make_score(confidence_score=1.5)
    validator = FieldValidator()
    results = await validator.validate(score, _make_case())
    failures = [r for r in results if not r.passed and r.severity == "CRITICAL"]
    assert any("confidence_score" in r.message for r in failures)


@pytest.mark.asyncio
async def test_field_validator_empty_outreach_angle() -> None:
    score = _make_score(outreach_angle="")
    validator = FieldValidator()
    results = await validator.validate(score, _make_case())
    warnings = [r for r in results if not r.passed and r.severity == "WARNING"]
    assert any("outreach_angle" in r.message for r in warnings)


@pytest.mark.asyncio
async def test_field_validator_expected_range_warning() -> None:
    score = _make_score(thesis_alignment=20)
    case = _make_case(expected_ranges={"thesis_alignment": [70, 95]})
    validator = FieldValidator()
    results = await validator.validate(score, case)
    warnings = [r for r in results if not r.passed and r.severity == "WARNING"]
    assert any("outside expected range" in r.message for r in warnings)


@pytest.mark.asyncio
async def test_field_validator_null_sci_reg() -> None:
    score = _make_score(scientific_regulatory_fit=None)
    validator = FieldValidator()
    results = await validator.validate(score, _make_case())
    # Should not fail — None is valid for scientific_regulatory_fit
    critical = [r for r in results if not r.passed and r.severity == "CRITICAL"]
    assert not critical


# --- ComputationValidator ---

@pytest.mark.asyncio
async def test_computation_validator_with_evidence() -> None:
    score = _make_score()
    weights = {
        "thesis_alignment": 0.30, "stage_fit": 0.25, "check_size_fit": 0.15,
        "scientific_regulatory_fit": 0.15, "recency": 0.10, "geography": 0.05,
    }
    validator = ComputationValidator(weights=weights, evidence_penalty=0.25)
    results = await validator.validate(score, _make_case())
    assert all(r.passed for r in results)
    # Check computed overall is present
    computation = [r for r in results if r.validator_name == "computation"]
    assert len(computation) >= 1


@pytest.mark.asyncio
async def test_computation_validator_no_evidence_penalty() -> None:
    score = _make_score(evidence_urls=[])
    weights = {
        "thesis_alignment": 0.30, "stage_fit": 0.25, "check_size_fit": 0.15,
        "scientific_regulatory_fit": 0.15, "recency": 0.10, "geography": 0.05,
    }
    validator = ComputationValidator(weights=weights, evidence_penalty=0.25)
    results = await validator.validate(score, _make_case())
    penalty_results = [r for r in results if "penalty" in r.message.lower()]
    assert len(penalty_results) == 1
    assert "0.25" in penalty_results[0].message


@pytest.mark.asyncio
async def test_computation_validator_null_sci_reg_redistribution() -> None:
    score = _make_score(scientific_regulatory_fit=None)
    weights = {
        "thesis_alignment": 0.30, "stage_fit": 0.25, "check_size_fit": 0.15,
        "scientific_regulatory_fit": 0.15, "recency": 0.10, "geography": 0.05,
    }
    validator = ComputationValidator(weights=weights, evidence_penalty=0.25)
    results = await validator.validate(score, _make_case())
    computation = [r for r in results if "overall computed" in r.message.lower()]
    assert len(computation) == 1
    assert computation[0].details["sci_reg_null"] is True


# --- UrlValidator ---

@pytest.mark.asyncio
async def test_url_validator_no_urls() -> None:
    score = _make_score(evidence_urls=[])
    validator = UrlValidator(skip_reachability=True)
    results = await validator.validate(score, _make_case())
    assert len(results) == 1
    assert results[0].passed


@pytest.mark.asyncio
async def test_url_validator_valid_format() -> None:
    score = _make_score(evidence_urls=["https://example.com/report"])
    validator = UrlValidator(skip_reachability=True)
    results = await validator.validate(score, _make_case())
    assert all(r.passed for r in results)


@pytest.mark.asyncio
async def test_url_validator_invalid_format() -> None:
    score = _make_score(evidence_urls=["not-a-url", "ftp://weird/path"])
    validator = UrlValidator(skip_reachability=True)
    results = await validator.validate(score, _make_case())
    failures = [r for r in results if not r.passed]
    assert len(failures) == 2


@pytest.mark.asyncio
async def test_url_validator_mixed() -> None:
    score = _make_score(evidence_urls=["https://example.com", "bad-url"])
    validator = UrlValidator(skip_reachability=True)
    results = await validator.validate(score, _make_case())
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    assert len(passed) == 1
    assert len(failed) == 1
