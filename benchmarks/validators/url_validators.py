from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from app.services.llm_client import LlmInvestorScore

from benchmarks.validators.base import BenchmarkCase, ValidationResult

logger = logging.getLogger(__name__)

_URL_CHECK_TIMEOUT = 5.0


class UrlValidator:
    """Validates evidence URL format and reachability."""

    def __init__(self, *, skip_reachability: bool = False) -> None:
        self._skip_reachability = skip_reachability

    async def validate(
        self, score: LlmInvestorScore, test_case: BenchmarkCase
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []

        if not score.evidence_urls:
            results.append(ValidationResult(
                validator_name="url",
                passed=True,
                severity="INFO",
                message="No evidence URLs to validate",
            ))
            return results

        for url in score.evidence_urls:
            # Format check
            try:
                parsed = urlparse(url)
                if not all([parsed.scheme, parsed.netloc]):
                    results.append(ValidationResult(
                        validator_name="url",
                        passed=False,
                        severity="WARNING",
                        message=f"Invalid URL format: {url}",
                        details={"url": url, "check": "format"},
                    ))
                    continue
            except Exception:
                results.append(ValidationResult(
                    validator_name="url",
                    passed=False,
                    severity="WARNING",
                    message=f"URL parse error: {url}",
                    details={"url": url, "check": "format"},
                ))
                continue

            if parsed.scheme not in ("http", "https"):
                results.append(ValidationResult(
                    validator_name="url",
                    passed=False,
                    severity="WARNING",
                    message=f"Non-HTTP scheme: {url}",
                    details={"url": url, "scheme": parsed.scheme},
                ))
                continue

            results.append(ValidationResult(
                validator_name="url",
                passed=True,
                severity="INFO",
                message=f"Valid URL format: {url}",
                details={"url": url, "check": "format"},
            ))

            # Reachability check (HEAD request)
            if self._skip_reachability:
                continue

            try:
                async with httpx.AsyncClient(
                    timeout=_URL_CHECK_TIMEOUT,
                    follow_redirects=True,
                ) as client:
                    resp = await client.head(url)
                    if resp.status_code < 400:
                        results.append(ValidationResult(
                            validator_name="url",
                            passed=True,
                            severity="INFO",
                            message=f"URL reachable: {url} ({resp.status_code})",
                            details={"url": url, "status": resp.status_code, "check": "reachability"},
                        ))
                    else:
                        results.append(ValidationResult(
                            validator_name="url",
                            passed=False,
                            severity="WARNING",
                            message=f"URL returned {resp.status_code}: {url}",
                            details={"url": url, "status": resp.status_code, "check": "reachability"},
                        ))
            except httpx.TimeoutException:
                results.append(ValidationResult(
                    validator_name="url",
                    passed=False,
                    severity="WARNING",
                    message=f"URL timeout ({_URL_CHECK_TIMEOUT}s): {url}",
                    details={"url": url, "check": "reachability", "error": "timeout"},
                ))
            except httpx.HTTPError as exc:
                logger.debug("URL check failed for %s: %s", url, exc)
                results.append(ValidationResult(
                    validator_name="url",
                    passed=False,
                    severity="WARNING",
                    message=f"URL unreachable: {url}",
                    details={"url": url, "check": "reachability", "error": str(exc)},
                ))

        return results
