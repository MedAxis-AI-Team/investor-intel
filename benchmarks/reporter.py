from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_summary(output_dir: Path) -> dict:
    """Read all evaluation runs and produce a summary with trends."""
    jsonl_path = output_dir / "evaluation_runs.jsonl"
    if not jsonl_path.exists():
        return {"error": "No evaluation runs found"}

    runs: list[dict] = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                runs.append(json.loads(line))

    if not runs:
        return {"error": "No evaluation runs found"}

    latest = runs[-1]

    # Trend data (last 10 runs)
    recent = runs[-10:]
    hit_rates = [r["hit_rate"] for r in recent if r.get("hit_rate") is not None]
    pass_rates = [r["validation_pass_rate"] for r in recent if r.get("validation_pass_rate") is not None]

    summary = {
        "latest_run": {
            "run_id": latest["run_id"],
            "timestamp": latest["timestamp"],
            "total_cases": latest["total_cases"],
            "hit_rate": latest.get("hit_rate"),
            "validation_pass_rate": latest.get("validation_pass_rate"),
        },
        "confusion_matrix": latest.get("confusion"),
        "calibration": latest.get("calibration"),
        "total_runs": len(runs),
        "trends": {
            "hit_rate_history": hit_rates,
            "validation_pass_rate_history": pass_rates,
            "hit_rate_mean": round(statistics.mean(hit_rates), 4) if hit_rates else None,
            "hit_rate_std": round(statistics.stdev(hit_rates), 4) if len(hit_rates) >= 2 else None,
            "improving": _is_improving(hit_rates),
        },
        "target": {
            "min_hit_rate": 0.30,
            "target_hit_rate": 0.50,
            "meeting_minimum": (latest.get("hit_rate") or 0) >= 0.30,
            "meeting_target": (latest.get("hit_rate") or 0) >= 0.50,
        },
    }

    # Write summary
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Summary written to %s", summary_path)

    return summary


def _is_improving(values: list[float]) -> bool | None:
    """Check if the trend is improving (last 3 values increasing)."""
    if len(values) < 3:
        return None
    return values[-1] > values[-3]


def print_summary(summary: dict) -> None:
    """Print human-readable summary to stdout."""
    latest = summary.get("latest_run", {})
    hit_rate = latest.get("hit_rate")
    pass_rate = latest.get("validation_pass_rate")

    print("\n" + "=" * 60)
    print("  BENCHMARK EVALUATION SUMMARY")
    print("=" * 60)

    print(f"\n  Run:       {latest.get('run_id', 'N/A')}")
    print(f"  Timestamp: {latest.get('timestamp', 'N/A')}")
    print(f"  Cases:     {latest.get('total_cases', 0)}")

    print(f"\n  Hit Rate (tier accuracy):  ", end="")
    if hit_rate is not None:
        pct = hit_rate * 100
        status = "PASS" if hit_rate >= 0.30 else "BELOW TARGET"
        print(f"{pct:.1f}% [{status}]")
    else:
        print("N/A")

    print(f"  Validation Pass Rate:      ", end="")
    if pass_rate is not None:
        print(f"{pass_rate * 100:.1f}%")
    else:
        print("N/A")

    # Confusion matrix
    confusion = summary.get("confusion_matrix")
    if confusion:
        print(f"\n  Confusion Matrix (rows=actual, cols=predicted):")
        labels = confusion.get("labels", [])
        matrix = confusion.get("matrix", [])
        header = "         " + "  ".join(f"{l:>8}" for l in labels)
        print(f"  {header}")
        for i, row in enumerate(matrix):
            row_str = "  ".join(f"{v:>8}" for v in row)
            print(f"  {labels[i]:>8} {row_str}")

        print(f"\n  Precision (weighted): {confusion.get('precision_weighted', 0):.2%}")
        print(f"  Recall (weighted):    {confusion.get('recall_weighted', 0):.2%}")
        print(f"  F1 (weighted):        {confusion.get('f1_weighted', 0):.2%}")

    # Calibration
    cal = summary.get("calibration")
    if cal:
        print(f"\n  Calibration:")
        print(f"    Samples:  {cal.get('samples_collected', 0)} / {cal.get('samples_needed', 30)}")
        ece = cal.get("ece")
        if ece is not None:
            print(f"    ECE:      {ece:.4f}")
        else:
            print(f"    ECE:      Not enough samples yet")

    # Trends
    trends = summary.get("trends", {})
    history = trends.get("hit_rate_history", [])
    if len(history) >= 2:
        print(f"\n  Trend ({len(history)} runs): ", end="")
        for h in history:
            print(f"{h:.0%} ", end="")
        improving = trends.get("improving")
        if improving is True:
            print("[IMPROVING]")
        elif improving is False:
            print("[DECLINING]")
        else:
            print("[INSUFFICIENT DATA]")

    # Target
    target = summary.get("target", {})
    print(f"\n  Target: {target.get('min_hit_rate', 0.30):.0%}-{target.get('target_hit_rate', 0.50):.0%}")
    if target.get("meeting_target"):
        print("  Status: MEETING TARGET")
    elif target.get("meeting_minimum"):
        print("  Status: ABOVE MINIMUM, BELOW TARGET")
    else:
        print("  Status: BELOW MINIMUM")

    print("\n" + "=" * 60)
