from __future__ import annotations

from typing import Mapping

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "proxy-authorization",
}


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        k: ("[REDACTED]" if k.lower() in SENSITIVE_HEADER_NAMES else v) for k, v in headers.items()
    }
