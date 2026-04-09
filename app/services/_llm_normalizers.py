"""LLM output normalization and enforcement per LLM Output Contract.

All LLM responses are untrusted. This module provides:
- Enum normalization via lookup tables (signal_type, x_signal_type, window, priority)
- Exact-string enforcement (suggested_contact)
- Deterministic computation (expires_relevance)
- Content filtering (FDA/regulatory term detection)

Prompt instructions are defense-in-depth only — code here is the enforcement layer.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Signal type normalization (analyze_signal output)
# ---------------------------------------------------------------------------

_SIGNAL_TYPE_SPEC = frozenset({
    "fund_close", "fda_clearance", "funding_announcement", "conference",
    "thought_leadership", "partnership", "exec_move", "proposed_rule",
    "draft_guidance", "fda_notice", "portfolio_milestone", "other",
})

_SIGNAL_TYPE_MAP: dict[str, str] = {
    "fundraise": "fund_close",
    "fund_raise": "fund_close",
    "fundraising": "fund_close",
    "fund close": "fund_close",
    "fda": "fda_clearance",
    "fda_approval": "fda_clearance",
    "regulatory": "fda_clearance",
    "funding": "funding_announcement",
    "investment": "funding_announcement",
    "leadership": "thought_leadership",
    "thought leadership": "thought_leadership",
    "hire": "exec_move",
    "executive": "exec_move",
    "exec": "exec_move",
    "rule": "proposed_rule",
    "guidance": "draft_guidance",
    "notice": "fda_notice",
    "milestone": "portfolio_milestone",
}


def normalize_signal_type(raw: str) -> str:
    """Map LLM signal_type output to the canonical spec enum. Falls back to 'other'."""
    lower = raw.strip().lower()
    if lower in _SIGNAL_TYPE_SPEC:
        return lower
    return _SIGNAL_TYPE_MAP.get(lower, "other")


# ---------------------------------------------------------------------------
# X signal type normalization (x_grok-specific output)
# ---------------------------------------------------------------------------

_X_SIGNAL_TYPE_SPEC = frozenset({
    "thesis_statement", "conference_signal", "fund_activity",
    "portfolio_mention", "hiring_signal", "general_activity",
})

_X_SIGNAL_TYPE_MAP: dict[str, str] = {
    "thesis": "thesis_statement",
    "investment_thesis": "thesis_statement",
    "conference": "conference_signal",
    "event": "conference_signal",
    "fund": "fund_activity",
    "funding": "fund_activity",
    "investment": "fund_activity",
    "portfolio": "portfolio_mention",
    "company_mention": "portfolio_mention",
    "hiring": "hiring_signal",
    "hire": "hiring_signal",
    "recruitment": "hiring_signal",
    "general": "general_activity",
    "activity": "general_activity",
}


def normalize_x_signal_type(raw: str | None) -> str | None:
    """Map LLM x_signal_type to canonical enum. Returns None if input is None."""
    if raw is None:
        return None
    lower = raw.strip().lower()
    if lower in _X_SIGNAL_TYPE_SPEC:
        return lower
    return _X_SIGNAL_TYPE_MAP.get(lower, "general_activity")


# ---------------------------------------------------------------------------
# Window and priority normalization (digest x_activity_section)
# ---------------------------------------------------------------------------

_WINDOW_SPEC = frozenset({"immediate", "this_week", "monitor"})
_PRIORITY_SPEC = frozenset({"high", "medium", "low"})
_PRIORITY_UPPER_SPEC = frozenset({"HIGH", "MEDIUM", "LOW"})


def normalize_window(raw: str) -> str:
    """Normalize window to immediate|this_week|monitor. Falls back to 'monitor'."""
    lower = raw.strip().lower()
    if lower in _WINDOW_SPEC:
        return lower
    return "monitor"


def normalize_priority(raw: str) -> str:
    """Normalize priority to lowercase high|medium|low. Falls back to 'medium'."""
    lower = raw.strip().lower()
    if lower in _PRIORITY_SPEC:
        return lower
    return "medium"


def normalize_priority_upper(raw: str) -> str:
    """Normalize priority to uppercase HIGH|MEDIUM|LOW for analyze_signal."""
    upper = raw.strip().upper()
    if upper in _PRIORITY_UPPER_SPEC:
        return upper
    return "MEDIUM"


# ---------------------------------------------------------------------------
# Expiry date computation (deterministic — never from LLM)
# ---------------------------------------------------------------------------

_EXPIRY_DAYS: dict[str, int] = {
    "fund_close": 14,
    "fda_clearance": 30,
    "funding_announcement": 21,
    "conference": 7,
    "thought_leadership": 30,
    "partnership": 21,
    "exec_move": 30,
    "proposed_rule": 60,
    "draft_guidance": 60,
    "fda_notice": 60,
    "portfolio_milestone": 14,
    "other": 14,
}


def compute_expiry(signal_type: str, published_at: str | None) -> str:
    """Compute expires_relevance date from signal type + published date.

    Uses published_at as base if parseable, otherwise falls back to today.
    Tries multiple ISO date formats to handle LLM/upstream variance.
    """
    base = datetime.now()
    if published_at:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                base = datetime.strptime(published_at.strip()[:19], fmt)
                break
            except ValueError:
                continue
    days = _EXPIRY_DAYS.get(signal_type, 14)
    return (base + timedelta(days=days)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# FDA/regulatory term detection (content filtering)
# ---------------------------------------------------------------------------

_POSITIVE_REG_TERMS = re.compile(
    r"\b(510\(k\)|pma|de\s*novo|clinical\s+trials?|eua|premarket)\b",
    re.IGNORECASE,
)

_NEGATED_FDA = re.compile(
    r"\b(no|not|without|non[- ]?)(\s+\w+){0,2}\s*\bfda\b",
    re.IGNORECASE,
)

_AFFIRM_FDA = re.compile(r"\bfda\b", re.IGNORECASE)


def needs_sci_reg(client_thesis: str) -> bool:
    """Return True only if the client thesis positively references FDA/regulatory terms.

    Handles negation (e.g. 'no FDA pathway') — returns False for negated mentions.
    Used to decide whether scientific_regulatory_fit should be scored or set to null.
    """
    if _POSITIVE_REG_TERMS.search(client_thesis):
        return True
    if not _AFFIRM_FDA.search(client_thesis):
        return False
    return not _NEGATED_FDA.search(client_thesis)


# ---------------------------------------------------------------------------
# Exact-string enforcement (suggested_contact)
# ---------------------------------------------------------------------------

_GENERIC_ROLES = re.compile(
    r"^(managing|general|senior|junior|founding)?\s*"
    r"(partner|director|manager|associate|analyst|principal|vp|"
    r"vice president|fund manager|investment officer|ceo|cfo|coo|cto|"
    r"head of|chief|board member)",
    re.IGNORECASE,
)


def enforce_suggested_contact(value: str, investor_notes: str | None) -> str:
    """Return 'Not identified' if the LLM returned a generic role instead of a named person.

    The spec requires a named individual — not a title like 'Managing Partner'.
    Uses regex to detect generic role patterns and replace with the exact fallback string.
    """
    cleaned = value.strip()
    if not cleaned:
        return "Not identified"
    if _GENERIC_ROLES.match(cleaned):
        return "Not identified"
    return cleaned


# ---------------------------------------------------------------------------
# Investor scoring normalization (score_investors output)
# ---------------------------------------------------------------------------

def bucket_score(raw: int | None, high: int = 70, mid: int = 45) -> str | None:
    """Convert raw 0–100 axis score to 'High' / 'Medium' / 'Low'.

    Returns None if raw is None (e.g. scientific_regulatory_fit not scored).
    Thresholds: ≥high → 'High', ≥mid → 'Medium', else → 'Low'.
    """
    if raw is None:
        return None
    if raw >= high:
        return "High"
    if raw >= mid:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# Grant confidence normalization (score_grants output)
# ---------------------------------------------------------------------------

_GRANT_CONFIDENCE_MAP: dict[str, str] = {
    "high": "high", "very high": "high", "strong": "high",
    "medium": "medium", "moderate": "medium",
    "low": "low", "weak": "low",
}


def normalize_grant_confidence(raw: str) -> str:
    """Normalize LLM confidence string to high|medium|low. Falls back to 'medium'."""
    return _GRANT_CONFIDENCE_MAP.get(raw.lower().strip(), "medium")


def compute_investor_tier(composite_score: int) -> str:
    """Derive investor tier from composite score (deterministic, never from LLM).

    Tier 1 ≥75 · Tier 2 ≥60 · Below Threshold <60.
    """
    if composite_score >= 75:
        return "Tier 1"
    if composite_score >= 60:
        return "Tier 2"
    return "Below Threshold"
