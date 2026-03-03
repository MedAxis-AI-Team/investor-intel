from __future__ import annotations

from dataclasses import dataclass

from app.models.common import Confidence, ConfidenceTier


@dataclass(frozen=True)
class ConfidencePolicy:
    high_threshold: float
    medium_threshold: float
    missing_evidence_penalty: float


def to_confidence(score: float, *, policy: ConfidencePolicy) -> Confidence:
    tier: ConfidenceTier
    if score >= policy.high_threshold:
        tier = "HIGH"
    elif score >= policy.medium_threshold:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return Confidence(score=score, tier=tier)


def penalize_for_missing_evidence(score: float, evidence_urls: list[str], *, policy: ConfidencePolicy) -> float:
    if evidence_urls:
        return score
    return max(0.0, score - policy.missing_evidence_penalty)
