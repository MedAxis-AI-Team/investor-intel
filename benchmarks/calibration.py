from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_MIN_SAMPLES_FOR_CALIBRATION = 30


@dataclass
class CalibrationSample:
    raw_confidence: float
    actual_correct: bool


@dataclass
class CalibrationResult:
    ece: float | None
    samples_collected: int
    samples_needed: int
    calibration_ready: bool
    bin_stats: list[dict] | None = None


class ConfidenceCalibrator:
    """Collects raw confidence vs actual correctness and computes calibration metrics.

    Uses Expected Calibration Error (ECE) with equal-width bins.
    When sklearn is available and enough samples exist, fits Platt scaling.
    """

    def __init__(self, *, num_bins: int = 10) -> None:
        self._samples: list[CalibrationSample] = []
        self._num_bins = num_bins
        self._platt_model: object | None = None

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def add_sample(self, raw_confidence: float, actual_correct: bool) -> None:
        self._samples.append(CalibrationSample(
            raw_confidence=raw_confidence,
            actual_correct=actual_correct,
        ))

    def compute_ece(self) -> CalibrationResult:
        """Compute Expected Calibration Error across bins."""
        n = len(self._samples)
        if n < _MIN_SAMPLES_FOR_CALIBRATION:
            return CalibrationResult(
                ece=None,
                samples_collected=n,
                samples_needed=_MIN_SAMPLES_FOR_CALIBRATION,
                calibration_ready=False,
            )

        bin_width = 1.0 / self._num_bins
        bin_stats: list[dict] = []
        ece = 0.0

        for b in range(self._num_bins):
            low = b * bin_width
            high = (b + 1) * bin_width

            bin_samples = [
                s for s in self._samples
                if low <= s.raw_confidence < high or (b == self._num_bins - 1 and s.raw_confidence == 1.0)
            ]

            if not bin_samples:
                bin_stats.append({
                    "bin": f"[{low:.1f}, {high:.1f})",
                    "count": 0,
                    "avg_confidence": 0.0,
                    "accuracy": 0.0,
                    "gap": 0.0,
                })
                continue

            avg_conf = sum(s.raw_confidence for s in bin_samples) / len(bin_samples)
            accuracy = sum(1 for s in bin_samples if s.actual_correct) / len(bin_samples)
            gap = abs(avg_conf - accuracy)

            ece += (len(bin_samples) / n) * gap

            bin_stats.append({
                "bin": f"[{low:.1f}, {high:.1f})",
                "count": len(bin_samples),
                "avg_confidence": round(avg_conf, 4),
                "accuracy": round(accuracy, 4),
                "gap": round(gap, 4),
            })

        return CalibrationResult(
            ece=round(ece, 4),
            samples_collected=n,
            samples_needed=_MIN_SAMPLES_FOR_CALIBRATION,
            calibration_ready=True,
            bin_stats=bin_stats,
        )

    def fit_platt_scaling(self) -> bool:
        """Fit Platt scaling (logistic regression) if sklearn is available."""
        if len(self._samples) < _MIN_SAMPLES_FOR_CALIBRATION:
            logger.info(
                "Not enough samples for Platt scaling (%d/%d)",
                len(self._samples), _MIN_SAMPLES_FOR_CALIBRATION,
            )
            return False

        try:
            from sklearn.linear_model import LogisticRegression
            import numpy as np
        except ImportError:
            logger.info("sklearn not available — skipping Platt scaling")
            return False

        X = np.array([[s.raw_confidence] for s in self._samples])
        y = np.array([int(s.actual_correct) for s in self._samples])

        if len(set(y)) < 2:
            logger.warning("All samples have same correctness — cannot fit Platt scaling")
            return False

        model = LogisticRegression(solver="lbfgs", max_iter=1000)
        model.fit(X, y)
        self._platt_model = model
        logger.info("Platt scaling fitted on %d samples", len(self._samples))
        return True

    def calibrate(self, raw_confidence: float) -> float:
        """Apply Platt scaling to a raw confidence score."""
        if self._platt_model is None:
            return raw_confidence

        try:
            import numpy as np
            proba = self._platt_model.predict_proba(np.array([[raw_confidence]]))[0][1]
            return float(proba)
        except Exception:
            return raw_confidence

    def save_samples(self, path: Path) -> None:
        """Persist samples to JSONL for accumulation across runs."""
        with open(path, "a") as f:
            for sample in self._samples:
                f.write(json.dumps({
                    "raw_confidence": sample.raw_confidence,
                    "actual_correct": sample.actual_correct,
                }) + "\n")

    def load_samples(self, path: Path) -> None:
        """Load previously collected samples from JSONL."""
        if not path.exists():
            return
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                self._samples.append(CalibrationSample(
                    raw_confidence=data["raw_confidence"],
                    actual_correct=data["actual_correct"],
                ))
        logger.info("Loaded %d historical calibration samples", len(self._samples))
