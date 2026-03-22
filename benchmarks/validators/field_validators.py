from __future__ import annotations

from app.services.llm_client import LlmInvestorScore

from benchmarks.validators.base import BenchmarkCase, ValidationResult


class FieldValidator:
    """Validates score ranges, types, and field presence."""

    async def validate(
        self, score: LlmInvestorScore, test_case: BenchmarkCase
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []

        # Axis score range checks (0-100)
        axis_fields = {
            "thesis_alignment": score.thesis_alignment,
            "stage_fit": score.stage_fit,
            "check_size_fit": score.check_size_fit,
            "recency": score.recency,
            "geography": score.geography,
        }
        if score.scientific_regulatory_fit is not None:
            axis_fields["scientific_regulatory_fit"] = score.scientific_regulatory_fit

        for field_name, value in axis_fields.items():
            if not isinstance(value, int):
                results.append(ValidationResult(
                    validator_name="field",
                    passed=False,
                    severity="CRITICAL",
                    message=f"{field_name} must be int, got {type(value).__name__}",
                    details={"field": field_name, "value": value},
                ))
            elif not (0 <= value <= 100):
                results.append(ValidationResult(
                    validator_name="field",
                    passed=False,
                    severity="CRITICAL",
                    message=f"{field_name}={value} out of range [0, 100]",
                    details={"field": field_name, "value": value},
                ))
            else:
                results.append(ValidationResult(
                    validator_name="field",
                    passed=True,
                    severity="INFO",
                    message=f"{field_name}={value} in valid range",
                ))

        # Confidence score range (0.0-1.0)
        if not (0.0 <= score.confidence_score <= 1.0):
            results.append(ValidationResult(
                validator_name="field",
                passed=False,
                severity="CRITICAL",
                message=f"confidence_score={score.confidence_score} out of range [0.0, 1.0]",
                details={"value": score.confidence_score},
            ))
        else:
            results.append(ValidationResult(
                validator_name="field",
                passed=True,
                severity="INFO",
                message=f"confidence_score={score.confidence_score:.2f} in valid range",
            ))

        # Required string fields non-empty
        for field_name, value in [
            ("outreach_angle", score.outreach_angle),
            ("suggested_contact", score.suggested_contact),
        ]:
            if not value or not value.strip():
                results.append(ValidationResult(
                    validator_name="field",
                    passed=False,
                    severity="WARNING",
                    message=f"{field_name} is empty",
                    details={"field": field_name},
                ))
            else:
                results.append(ValidationResult(
                    validator_name="field",
                    passed=True,
                    severity="INFO",
                    message=f"{field_name} present ({len(value)} chars)",
                ))

        # Evidence URLs type check
        if not isinstance(score.evidence_urls, list):
            results.append(ValidationResult(
                validator_name="field",
                passed=False,
                severity="CRITICAL",
                message=f"evidence_urls must be list, got {type(score.evidence_urls).__name__}",
            ))
        else:
            results.append(ValidationResult(
                validator_name="field",
                passed=True,
                severity="INFO",
                message=f"evidence_urls contains {len(score.evidence_urls)} items",
            ))

        # Expected range checks (soft validation — WARNING, not CRITICAL)
        for axis_name, value in axis_fields.items():
            range_key = f"{axis_name}"
            if range_key in test_case.expected_ranges:
                low, high = test_case.expected_ranges[range_key]
                if not (low <= value <= high):
                    results.append(ValidationResult(
                        validator_name="field",
                        passed=False,
                        severity="WARNING",
                        message=f"{axis_name}={value} outside expected range [{low}, {high}]",
                        details={"field": axis_name, "value": value, "expected_low": low, "expected_high": high},
                    ))

        return results


class ComputationValidator:
    """Validates weighted sum and confidence penalty logic."""

    def __init__(self, *, weights: dict[str, float], evidence_penalty: float) -> None:
        self._weights = weights
        self._evidence_penalty = evidence_penalty

    async def validate(
        self, score: LlmInvestorScore, test_case: BenchmarkCase
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []

        # Recompute weighted overall
        w = self._weights
        if score.scientific_regulatory_fit is not None:
            expected_overall = (
                score.thesis_alignment * w["thesis_alignment"]
                + score.stage_fit * w["stage_fit"]
                + score.check_size_fit * w["check_size_fit"]
                + score.scientific_regulatory_fit * w["scientific_regulatory_fit"]
                + score.recency * w["recency"]
                + score.geography * w["geography"]
            )
        else:
            redistributed_thesis = w["thesis_alignment"] + w["scientific_regulatory_fit"]
            expected_overall = (
                score.thesis_alignment * redistributed_thesis
                + score.stage_fit * w["stage_fit"]
                + score.check_size_fit * w["check_size_fit"]
                + score.recency * w["recency"]
                + score.geography * w["geography"]
            )

        expected_overall_int = int(round(expected_overall))
        results.append(ValidationResult(
            validator_name="computation",
            passed=True,
            severity="INFO",
            message=f"Weighted overall computed: {expected_overall_int}",
            details={
                "expected_overall": expected_overall_int,
                "raw_weighted": round(expected_overall, 4),
                "sci_reg_null": score.scientific_regulatory_fit is None,
            },
        ))

        # Validate confidence penalty logic
        raw_confidence = score.confidence_score
        if not score.evidence_urls:
            expected_confidence = max(0.0, raw_confidence - self._evidence_penalty)
            results.append(ValidationResult(
                validator_name="computation",
                passed=True,
                severity="WARNING",
                message=f"No evidence URLs — penalty of {self._evidence_penalty} should apply "
                        f"(raw={raw_confidence:.2f}, penalized={expected_confidence:.2f})",
                details={
                    "raw_confidence": raw_confidence,
                    "expected_penalized": expected_confidence,
                    "penalty": self._evidence_penalty,
                },
            ))
        else:
            results.append(ValidationResult(
                validator_name="computation",
                passed=True,
                severity="INFO",
                message=f"Evidence URLs present — no penalty (confidence={raw_confidence:.2f})",
            ))

        return results
