from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.config import get_settings

from benchmarks.reporter import generate_summary, print_summary
from benchmarks.runner import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run investor scoring benchmarks against the real LLM.",
        prog="python -m benchmarks.cli",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/dataset.json"),
        help="Path to benchmark dataset JSON (default: benchmarks/dataset.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/results"),
        help="Directory to store results (default: benchmarks/results/)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Run on first N test cases only (default: all)",
    )
    parser.add_argument(
        "--skip-url-check",
        action="store_true",
        help="Skip HTTP reachability checks for evidence URLs",
    )
    parser.add_argument(
        "--skip-consistency",
        action="store_true",
        help="Skip consistency validation (saves LLM calls)",
    )
    parser.add_argument(
        "--consistency-runs",
        type=int,
        default=3,
        help="Number of runs per case for consistency checks (default: 3)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Only print summary of previous runs, don't run new evaluation",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    if args.summary_only:
        summary = generate_summary(args.output)
        print_summary(summary)
        return

    settings = get_settings()

    result = asyncio.run(run_benchmark(
        dataset_path=args.dataset,
        output_dir=args.output,
        settings=settings,
        skip_url_check=args.skip_url_check,
        skip_consistency=args.skip_consistency,
        consistency_runs=args.consistency_runs,
        sample_size=args.sample_size,
    ))

    # Print results
    summary = generate_summary(args.output)
    print_summary(summary)

    # Exit code based on minimum hit rate
    if result.hit_rate is not None and result.hit_rate < 0.30:
        logging.getLogger(__name__).warning(
            "Hit rate %.1f%% is below minimum target of 30%%",
            result.hit_rate * 100,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
