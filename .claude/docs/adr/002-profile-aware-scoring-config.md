# ADR-002: Profile-Aware Scoring via Config-Object Pattern
Date: 2026-04-20
Status: accepted

## Context

The initial scoring pipeline assumed all clients were therapeutic biotech companies. The first real non-therapeutic test client (Predictive Healthcare — digital health + AI-enabled RPM) exposed that a single hardcoded therapeutic prompt produces the wrong investor universe and incorrectly gates the `scientific_regulatory_fit` axis on FDA keyword detection in the thesis text.

The `needs_sci_reg()` function was the right design for therapeutics (where sci_reg only applies if FDA work is in scope) but wrong for profiles like `medical_device` or `digital_health` where the axis always applies — just reframed (device pathway alignment, tech differentiation + clinical adoption).

Phase 1.5 of the scoring roadmap requires `scoring_instructions` to be injectable as JSON directly in the request, bypassing the profile builder. The architecture needed to support that swap without touching the prompt builder.

## Decision

Introduce a `ScoringInstructions` frozen dataclass as the single config object driving prompt construction. Profile and modifier branching is handled via lookup dicts in `scoring_config.py` — no if/else chains anywhere in the prompt path.

**Profiles (6):** `therapeutic`, `medical_device`, `diagnostics`, `digital_health`, `service_cro`, `platform_tools`

**Modifiers (4, additive):** `ai_enabled`, `rpm_saas`, `cross_border_ca`, `ruo_no_reg`

Key design decisions:
- `score_scientific_regulatory: bool` on `ScoringInstructions` overrides `needs_sci_reg()`. `therapeutic` sets it `False` (preserves existing behavior exactly). All other profiles set it `True` (always score, reframe axis per profile).
- `build_scoring_instructions(profile, modifiers)` is the only entry point. Unknown profiles fall back to `therapeutic` with a warning log. Unknown modifiers are silently ignored.
- `_build_profile_section()` in `anthropic_client.py` builds the `CLIENT PROFILE / PROFILE GUIDANCE / MODIFIER GUIDANCE` prompt block from `ScoringInstructions`. Returns `""` for therapeutic (no block injected — zero prompt change for existing clients).
- Classifier version (`1.0.0-phase1`) is logged with every scoring run and surfaced in `/health`.

**Phase 1.5 compatibility:** when `scoring_instructions` JSON is supplied directly in the request, parse it into `ScoringInstructions` and bypass `build_scoring_instructions()`. The prompt builder in `anthropic_client.py` requires zero changes.

## Consequences

### Positive
- Prompt branching is data-driven — adding a new profile or modifier is a dict entry, not a code change
- `therapeutic` profile is a no-op injection — zero behavioral change for existing clients
- `/health` now surfaces `scoring_classifier` version for observability
- Phase 1.5 swap is additive: new request field + new parser, prompt builder untouched
- All 115 existing tests pass without modification to test logic

### Negative
- `ScoringInstructions` frozen dataclass grows as more profiles/modifiers are added — needs a pruning policy eventually
- The `_CLASSIFIER_VERSION` string is manually bumped — not tied to git tags

### Risks
- Profile guidance text is LLM-injected prose — quality degrades if not reviewed when profiles are added. Review each profile's `investor_universe_hints` and `sci_reg_guidance` before activating with a live client.

## Implementation Notes
- `app/services/scoring_config.py` — `ScoringInstructions`, `_PROFILE_CONFIGS`, `_MODIFIER_CONFIGS`, `build_scoring_instructions()`
- `app/models/score_investors.py` — `ClientProfileType`, `ScoringModifier` Literals; `ClientProfile.client_profile` + `ClientProfile.modifiers` fields
- `app/services/llm_client.py` — `scoring_instructions` optional param on Protocol (TYPE_CHECKING guard to avoid circular import)
- `app/services/anthropic_client.py` — `_build_profile_section()`, `score_scientific_regulatory` override logic
- `app/services/scoring_service.py` — `build_scoring_instructions()` called before investor loop
- `migrations/002_client_profile.sql` — idempotent Supabase migration (reference SQL, not auto-applied)
