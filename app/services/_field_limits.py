from __future__ import annotations

# Field size limits for LLM-sourced output.
# Single source of truth — referenced by both the Pydantic response models
# (via max_length=) and the service truncation guards.
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

# analyze_signal field limits
SIGNAL_HEADLINE_MAX: int = 300
SIGNAL_WHY_MAX: int = 1000
SIGNAL_OUTREACH_MAX: int = 1000
SIGNAL_CONTACT_MAX: int = 200
SIGNAL_TIMESENS_MAX: int = 200
SIGNAL_RATIONALE_MAX: int = 4000

# score_grants field limits
GRANT_RATIONALE_MAX: int = 4000
GRANT_GUIDANCE_MAX: int = 4000

# generate_digest field limits
DIGEST_SUBJECT_MAX: int = 200
DIGEST_PREHEADER_MAX: int = 300
DIGEST_TITLE_MAX: int = 200
DIGEST_BULLET_MAX: int = 500
DIGEST_SIGNAL_SUMMARY_MAX: int = 1000
DIGEST_RECOMMENDED_ACTION_MAX: int = 500

# advisor prep field limits
ADVISOR_ANGLE_MAX: int = 1000
ADVISOR_AVOID_MAX: int = 500
ADVISOR_OPENING_MAX: int = 1000
ADVISOR_DESIRED_OUTCOME_MAX: int = 500
ADVISOR_OBJECTION_MAX: int = 500
ADVISOR_RESPONSE_MAX: int = 1000
ADVISOR_REENGAGEMENT_MAX: int = 1000
