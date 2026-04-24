from __future__ import annotations

# Field size limits for LLM-sourced investor scoring output.
# Single source of truth — referenced by both the Pydantic response models
# (via max_length=) and the service truncation guards in scoring_service.py.
# Changing a limit here updates both the API contract and the enforcement layer.

NARRATIVE_MAX: int = 2000
OUTREACH_MAX: int = 2000
AVOID_MAX: int = 1000
NOTES_MAX: int = 2000
# Applied at LLM parse time — 100 chars below NOTES_MAX to reserve space
# for the angel investor flag appended downstream in scoring_service.py.
NOTES_LLM_MAX: int = 1900
EVIDENCE_URLS_MAX: int = 20
TOP_CLAIMS_MAX: int = 5
