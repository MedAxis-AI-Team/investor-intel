from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.services.anthropic_client import AnthropicLlmClient
from app.services.confidence import ConfidencePolicy, to_confidence
from app.services.llm_client import LlmClient, LlmInvestorScore

from benchmarks.calibration import ConfidenceCalibrator
from benchmarks.confusion import ConfusionReport, build_confusion_report
from benchmarks.validators.base import BenchmarkCase, ValidationResult
from benchmarks.validators.consistency import ConsistencyValidator
from benchmarks.validators.field_validators import ComputationValidator, FieldValidator
from benchmarks.validators.url_validators import UrlValidator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaseResult:
    test_case_id: str
    test_case_name: str
    score_snapshot: dict
    predicted_tier: str
    expected_tier: str | None
    validations: list[dict]
    critical_failures: int
    warnings: int
    passed: int


@dataclass(frozen=True)
class RunResult:
    run_id: str
    timestamp: str
    total_cases: int
    case_results: list[CaseResult]
    confusion: dict | None
    calibration: dict | None
    hit_rate: float | None
    validation_pass_rate: float


def _load_dataset(path: Path) -> list[BenchmarkCase]:
    """Load benchmark dataset from JSON."""
    with open(path) as f:
        data = json.load(f)

    cases: list[BenchmarkCase] = []
    for tc in data["test_cases"]:
        expected = tc.get("expected", {})
        cases.append(BenchmarkCase(
            id=tc["id"],
            name=tc["name"],
            client_name=tc["client"]["name"],
            client_thesis=tc["client"]["thesis"],
            client_geography=tc["client"].get("geography"),
            client_funding_target=tc["client"].get("funding_target"),
            investor_name=tc["investor"]["name"],
            investor_notes=tc["investor"].get("notes"),
            expected_tier=expected.get("tier"),
            expected_ranges=expected.get("ranges", {}),
            scientific_regulatory_fit_applicable=expected.get(
                "scientific_regulatory_fit_applicable", True
            ),
        ))
    return cases


def _score_to_tier(confidence_score: float, policy: ConfidencePolicy) -> str:
    return to_confidence(confidence_score, policy=policy).tier


async def run_benchmark(
    *,
    dataset_path: Path,
    output_dir: Path,
    settings: Settings,
    llm: LlmClient | None = None,
    confidence_policy: ConfidencePolicy | None = None,
    weights: dict[str, float] | None = None,
    skip_url_check: bool = False,
    skip_consistency: bool = False,
    consistency_runs: int = 3,
    sample_size: int | None = None,
) -> RunResult:
    """Execute full benchmark evaluation.

    When called from the API endpoint, ``llm``, ``confidence_policy``, and
    ``weights`` are injected via FastAPI DI.  When called from the CLI they
    are built from ``settings``.
    """
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    logger.info("Starting benchmark run: %s", run_id)

    # Load dataset
    cases = _load_dataset(dataset_path)
    if sample_size and sample_size < len(cases):
        cases = cases[:sample_size]

    # Build LLM client from settings if not injected
    if llm is None:
        llm = AnthropicLlmClient(settings=settings)

    # Build confidence policy from settings if not injected
    if confidence_policy is None:
        confidence_policy = ConfidencePolicy(
            high_threshold=settings.confidence_high_threshold,
            medium_threshold=settings.confidence_medium_threshold,
            missing_evidence_penalty=settings.evidence_missing_penalty,
        )

    # Build weights dict from settings if not injected
    if weights is None:
        weights = {
            "thesis_alignment": settings.score_weight_thesis_alignment,
            "stage_fit": settings.score_weight_stage_fit,
            "check_size_fit": settings.score_weight_check_size_fit,
            "scientific_regulatory_fit": settings.score_weight_scientific_regulatory_fit,
            "recency": settings.score_weight_recency,
            "geography": settings.score_weight_geography,
        }

    # Build validators
    field_validator = FieldValidator()
    computation_validator = ComputationValidator(
        weights=weights,
        evidence_penalty=settings.evidence_missing_penalty,
    )
    url_validator = UrlValidator(skip_reachability=skip_url_check)

    consistency_validator: ConsistencyValidator | None = None
    if not skip_consistency:
        consistency_validator = ConsistencyValidator(
            llm=llm,
            num_runs=consistency_runs,
        )

    # Calibration
    calibrator = ConfidenceCalibrator()
    calibration_samples_path = output_dir / "calibration_samples.jsonl"
    calibrator.load_samples(calibration_samples_path)

    # Run evaluations
    case_results: list[CaseResult] = []
    y_true: list[str] = []
    y_pred: list[str] = []

    for tc in cases:
        logger.info("Evaluating: %s (%s)", tc.name, tc.id)

        try:
            llm_score = await llm.score_investor(
                client_name=tc.client_name,
                client_thesis=tc.client_thesis,
                client_geography=tc.client_geography,
                client_funding_target=tc.client_funding_target,
                investor_name=tc.investor_name,
                investor_notes=tc.investor_notes,
            )
        except Exception as exc:
            logger.error("LLM call failed for %s: %s", tc.id, exc)
            case_results.append(CaseResult(
                test_case_id=tc.id,
                test_case_name=tc.name,
                score_snapshot={},
                predicted_tier="ERROR",
                expected_tier=tc.expected_tier,
                validations=[{
                    "validator_name": "runner",
                    "passed": False,
                    "severity": "CRITICAL",
                    "message": f"LLM call failed: {exc}",
                }],
                critical_failures=1,
                warnings=0,
                passed=0,
            ))
            continue

        # Determine predicted tier
        predicted_tier = _score_to_tier(llm_score.confidence_score, confidence_policy)

        # Run all validators
        all_validations: list[ValidationResult] = []
        all_validations.extend(await field_validator.validate(llm_score, tc))
        all_validations.extend(await computation_validator.validate(llm_score, tc))
        all_validations.extend(await url_validator.validate(llm_score, tc))

        if consistency_validator:
            all_validations.extend(await consistency_validator.validate(llm_score, tc))

        # Tally results
        critical = sum(1 for v in all_validations if not v.passed and v.severity == "CRITICAL")
        warnings = sum(1 for v in all_validations if not v.passed and v.severity == "WARNING")
        passed = sum(1 for v in all_validations if v.passed)

        # Score snapshot
        snapshot = {
            "thesis_alignment": llm_score.thesis_alignment,
            "stage_fit": llm_score.stage_fit,
            "check_size_fit": llm_score.check_size_fit,
            "scientific_regulatory_fit": llm_score.scientific_regulatory_fit,
            "recency": llm_score.recency,
            "geography": llm_score.geography,
            "confidence_score": llm_score.confidence_score,
            "evidence_urls": llm_score.evidence_urls,
            "outreach_angle": llm_score.outreach_angle[:100],
            "suggested_contact": llm_score.suggested_contact,
        }

        case_results.append(CaseResult(
            test_case_id=tc.id,
            test_case_name=tc.name,
            score_snapshot=snapshot,
            predicted_tier=predicted_tier,
            expected_tier=tc.expected_tier,
            validations=[
                {
                    "validator_name": v.validator_name,
                    "passed": v.passed,
                    "severity": v.severity,
                    "message": v.message,
                }
                for v in all_validations
            ],
            critical_failures=critical,
            warnings=warnings,
            passed=passed,
        ))

        # Confusion matrix tracking
        if tc.expected_tier:
            y_true.append(tc.expected_tier)
            y_pred.append(predicted_tier)

        # Calibration tracking
        if tc.expected_tier:
            actual_correct = predicted_tier == tc.expected_tier
            calibrator.add_sample(llm_score.confidence_score, actual_correct)

    # Build confusion report
    confusion_report: ConfusionReport | None = None
    if y_true:
        confusion_report = build_confusion_report(y_true, y_pred)

    # Compute calibration
    calibration_result = calibrator.compute_ece()
    calibrator.save_samples(calibration_samples_path)
    if calibration_result.calibration_ready:
        calibrator.fit_platt_scaling()

    # Hit rate = % of correct tier predictions
    hit_rate: float | None = None
    if y_true:
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
        hit_rate = round(correct / len(y_true), 4)

    # Validation pass rate
    total_validations = sum(r.passed + r.critical_failures + r.warnings for r in case_results)
    total_passed = sum(r.passed for r in case_results)
    validation_pass_rate = round(total_passed / total_validations, 4) if total_validations else 0.0

    run_result = RunResult(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_cases=len(case_results),
        case_results=case_results,
        confusion={
            "matrix": confusion_report.matrix,
            "labels": confusion_report.labels,
            "per_class": confusion_report.per_class,
            "precision_weighted": confusion_report.precision_weighted,
            "recall_weighted": confusion_report.recall_weighted,
            "f1_weighted": confusion_report.f1_weighted,
            "accuracy": confusion_report.accuracy,
        } if confusion_report else None,
        calibration={
            "ece": calibration_result.ece,
            "samples_collected": calibration_result.samples_collected,
            "samples_needed": calibration_result.samples_needed,
            "calibration_ready": calibration_result.calibration_ready,
        },
        hit_rate=hit_rate,
        validation_pass_rate=validation_pass_rate,
    )

    # Persist results
    output_dir.mkdir(parents=True, exist_ok=True)
    _persist_run(run_result, output_dir)

    return run_result


def _persist_run(result: RunResult, output_dir: Path) -> None:
    """Append run to JSONL and update summary."""
    # JSONL append
    jsonl_path = output_dir / "evaluation_runs.jsonl"
    run_data = {
        "run_id": result.run_id,
        "timestamp": result.timestamp,
        "total_cases": result.total_cases,
        "hit_rate": result.hit_rate,
        "validation_pass_rate": result.validation_pass_rate,
        "confusion": result.confusion,
        "calibration": result.calibration,
    }
    with open(jsonl_path, "a") as f:
        f.write(json.dumps(run_data) + "\n")

    # Full run detail
    detail_path = output_dir / f"{result.run_id}.json"
    full_data = {
        **run_data,
        "case_results": [
            {
                "test_case_id": cr.test_case_id,
                "test_case_name": cr.test_case_name,
                "score_snapshot": cr.score_snapshot,
                "predicted_tier": cr.predicted_tier,
                "expected_tier": cr.expected_tier,
                "critical_failures": cr.critical_failures,
                "warnings": cr.warnings,
                "passed": cr.passed,
                "validations": cr.validations,
            }
            for cr in result.case_results
        ],
    }
    with open(detail_path, "w") as f:
        json.dump(full_data, f, indent=2)

    logger.info("Results written to %s and %s", jsonl_path, detail_path)
