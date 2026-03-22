from __future__ import annotations

import tempfile
from pathlib import Path

from benchmarks.calibration import ConfidenceCalibrator


def test_insufficient_samples() -> None:
    cal = ConfidenceCalibrator()
    for _ in range(10):
        cal.add_sample(0.8, True)

    result = cal.compute_ece()
    assert result.ece is None
    assert result.calibration_ready is False
    assert result.samples_collected == 10
    assert result.samples_needed == 30


def test_ece_computation() -> None:
    cal = ConfidenceCalibrator(num_bins=5)

    # Add 30+ samples with known distribution
    # High confidence, correct
    for _ in range(15):
        cal.add_sample(0.9, True)
    # Low confidence, wrong
    for _ in range(15):
        cal.add_sample(0.2, False)

    result = cal.compute_ece()
    assert result.calibration_ready is True
    assert result.ece is not None
    # Well-calibrated: high confidence = correct, low confidence = wrong
    assert result.ece < 0.2  # Should be well-calibrated
    assert result.bin_stats is not None


def test_ece_badly_calibrated() -> None:
    cal = ConfidenceCalibrator(num_bins=5)

    # High confidence but wrong — badly calibrated
    for _ in range(30):
        cal.add_sample(0.95, False)

    result = cal.compute_ece()
    assert result.calibration_ready is True
    assert result.ece is not None
    assert result.ece > 0.5  # Should be very poorly calibrated


def test_save_and_load_samples() -> None:
    cal1 = ConfidenceCalibrator()
    cal1.add_sample(0.8, True)
    cal1.add_sample(0.3, False)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "samples.jsonl"
        cal1.save_samples(path)

        cal2 = ConfidenceCalibrator()
        cal2.load_samples(path)
        assert cal2.sample_count == 2


def test_calibrate_without_model_returns_raw() -> None:
    cal = ConfidenceCalibrator()
    assert cal.calibrate(0.75) == 0.75


def test_load_nonexistent_file() -> None:
    cal = ConfidenceCalibrator()
    cal.load_samples(Path("/nonexistent/path.jsonl"))
    assert cal.sample_count == 0
