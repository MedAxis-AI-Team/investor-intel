from __future__ import annotations

import statistics

from app.services.llm_client import LlmClient, LlmInvestorScore

from benchmarks.validators.base import BenchmarkCase, ValidationResult

_DEFAULT_VARIANCE_THRESHOLD = 15.0


class ConsistencyValidator:
    """Runs the same test case multiple times and measures variance."""

    def __init__(
        self,
        *,
        llm: LlmClient,
        num_runs: int = 3,
        variance_threshold: float = _DEFAULT_VARIANCE_THRESHOLD,
    ) -> None:
        self._llm = llm
        self._num_runs = num_runs
        self._variance_threshold = variance_threshold

    async def validate(
        self, score: LlmInvestorScore, test_case: BenchmarkCase
    ) -> list[ValidationResult]:
        """Run additional LLM calls and compare variance.

        The first score is already provided (from the main run).
        We run (num_runs - 1) additional calls.
        """
        all_scores: list[LlmInvestorScore] = [score]

        for _ in range(self._num_runs - 1):
            additional = await self._llm.score_investor(
                client_name=test_case.client_name,
                client_thesis=test_case.client_thesis,
                client_geography=test_case.client_geography,
                client_funding_target=test_case.client_funding_target,
                investor_name=test_case.investor_name,
                investor_notes=test_case.investor_notes,
            )
            all_scores.append(additional)

        results: list[ValidationResult] = []
        axis_names = [
            "thesis_alignment", "stage_fit", "check_size_fit",
            "recency", "geography",
        ]

        variance_details: dict[str, float] = {}

        for axis in axis_names:
            values = [getattr(s, axis) for s in all_scores]
            if len(values) < 2:
                continue

            std_dev = statistics.stdev(values)
            variance_details[axis] = round(std_dev, 2)

            if std_dev > self._variance_threshold:
                results.append(ValidationResult(
                    validator_name="consistency",
                    passed=False,
                    severity="WARNING",
                    message=f"{axis} high variance: std_dev={std_dev:.1f} "
                            f"(threshold={self._variance_threshold}), values={values}",
                    details={"axis": axis, "std_dev": std_dev, "values": values},
                ))
            else:
                results.append(ValidationResult(
                    validator_name="consistency",
                    passed=True,
                    severity="INFO",
                    message=f"{axis} consistent: std_dev={std_dev:.1f}, values={values}",
                    details={"axis": axis, "std_dev": std_dev, "values": values},
                ))

        # Overall summary
        if variance_details:
            mean_std = statistics.mean(variance_details.values())
            max_std = max(variance_details.values())
            results.append(ValidationResult(
                validator_name="consistency",
                passed=max_std <= self._variance_threshold,
                severity="INFO" if max_std <= self._variance_threshold else "WARNING",
                message=f"Overall consistency: mean_std={mean_std:.1f}, max_std={max_std:.1f}",
                details={"per_axis": variance_details, "num_runs": self._num_runs},
            ))

        return results
