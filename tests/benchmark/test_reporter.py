from __future__ import annotations

import json
import tempfile
from pathlib import Path

from benchmarks.reporter import generate_summary


def _write_run(output_dir: Path, run_id: str, hit_rate: float) -> None:
    jsonl_path = output_dir / "evaluation_runs.jsonl"
    with open(jsonl_path, "a") as f:
        f.write(json.dumps({
            "run_id": run_id,
            "timestamp": "2026-03-22T00:00:00Z",
            "total_cases": 10,
            "hit_rate": hit_rate,
            "validation_pass_rate": 0.95,
            "confusion": {
                "matrix": [[3, 1, 0], [0, 2, 1], [0, 0, 3]],
                "labels": ["HIGH", "MEDIUM", "LOW"],
                "precision_weighted": 0.85,
                "recall_weighted": 0.80,
                "f1_weighted": 0.82,
                "accuracy": 0.80,
            },
            "calibration": {
                "ece": None,
                "samples_collected": 10,
                "samples_needed": 30,
                "calibration_ready": False,
            },
        }) + "\n")


def test_generate_summary_single_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        _write_run(output_dir, "run_001", 0.42)

        summary = generate_summary(output_dir)
        assert summary["latest_run"]["hit_rate"] == 0.42
        assert summary["total_runs"] == 1
        assert summary["target"]["meeting_minimum"] is True
        assert summary["target"]["meeting_target"] is False


def test_generate_summary_multiple_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        _write_run(output_dir, "run_001", 0.35)
        _write_run(output_dir, "run_002", 0.40)
        _write_run(output_dir, "run_003", 0.45)

        summary = generate_summary(output_dir)
        assert summary["total_runs"] == 3
        assert summary["latest_run"]["hit_rate"] == 0.45
        assert summary["trends"]["hit_rate_history"] == [0.35, 0.40, 0.45]
        assert summary["trends"]["improving"] is True


def test_generate_summary_no_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        summary = generate_summary(Path(tmp))
        assert "error" in summary


def test_generate_summary_below_minimum() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        _write_run(output_dir, "run_001", 0.20)

        summary = generate_summary(output_dir)
        assert summary["target"]["meeting_minimum"] is False
        assert summary["target"]["meeting_target"] is False


def test_summary_writes_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        _write_run(output_dir, "run_001", 0.50)

        generate_summary(output_dir)
        summary_path = output_dir / "summary.json"
        assert summary_path.exists()
        data = json.loads(summary_path.read_text())
        assert data["latest_run"]["hit_rate"] == 0.50
