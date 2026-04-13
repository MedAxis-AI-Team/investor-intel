from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import Settings
from app.services._llm_normalizers import (
    compute_expiry,
    enforce_suggested_contact,
    needs_sci_reg,
    normalize_priority,
    normalize_priority_upper,
    normalize_signal_type,
    normalize_window,
    normalize_x_signal_type,
)
from app.services.llm_client import (
    LlmAdvisorCallPlan,
    LlmAdvisorObjection,
    LlmAdvisorOutreachAngle,
    LlmAdvisorPrep,
    LlmClient,
    LlmDigestResult,
    LlmGrantScore,
    LlmInvestorScore,
    LlmRetryExhaustedError,
    LlmSignalAnalysis,
    LlmSignalBriefing,
    LlmXActivitySection,
    LlmXActivitySignal,
)
from app.services.scoring_config import ScoringInstructions

_MAX_JSON_RETRIES = 2
_log = logging.getLogger(__name__)


def _build_profile_section(instructions: ScoringInstructions | None) -> str:
    """Build the CLIENT PROFILE prompt block from ScoringInstructions.

    Returns an empty string for None (therapeutic default without explicit instructions).
    The block is inserted before the SCORING AXES section so the LLM has full context
    on thesis keywords, investor universe, and axis reframes before scoring.
    """
    if instructions is None:
        return ""

    lines: list[str] = [
        f"\nCLIENT PROFILE: {instructions.profile_type}",
        "PROFILE GUIDANCE:",
    ]

    if instructions.thesis_keywords:
        keywords_str = ", ".join(instructions.thesis_keywords)
        lines.append(f"- Thesis keywords: {keywords_str}")

    lines.append(f"- Target investors: {instructions.investor_universe_hints}")
    lines.append(f"- Stage fit: {instructions.stage_fit_guidance}")
    lines.append(f"- Scientific/regulatory axis: {instructions.sci_reg_guidance}")

    if instructions.modifier_keywords or instructions.modifier_guidance:
        lines.append("\nMODIFIER GUIDANCE:")
        if instructions.modifier_keywords:
            mod_kw_str = ", ".join(instructions.modifier_keywords)
            lines.append(f"- Additional keywords: {mod_kw_str}")
        if instructions.modifier_guidance:
            lines.append(instructions.modifier_guidance)

    return "\n".join(lines) + "\n"


class AnthropicLlmClient(LlmClient):
    def __init__(self, *, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=settings.request_timeout_seconds)
        self._model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens

    async def _json_call(self, *, system: str, user: str) -> dict:
        last_raw = ""
        for attempt in range(_MAX_JSON_RETRIES + 1):
            current_system = system
            if attempt > 0:
                current_system = (
                    system
                    + " CRITICAL: Your previous response was not valid JSON."
                    " Return ONLY raw JSON — no markdown fences, no explanation, no preamble."
                )

            message = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=current_system,
                messages=[{"role": "user", "content": user}],
            )

            text = ""
            for block in message.content:
                if getattr(block, "type", None) == "text":
                    text += block.text

            # Extract JSON from the response, handling preamble and markdown fences
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0]
                text = text.strip()

            # If response has preamble before the JSON object/array, find it
            if text and not text[0] in ("{", "["):
                start = text.find("{")
                arr_start = text.find("[")
                if arr_start != -1 and (start == -1 or arr_start < start):
                    start = arr_start
                if start != -1:
                    text = text[start:]
                    # Trim any trailing non-JSON text after the closing brace/bracket
                    end = text.rfind("}") if text[0] == "{" else text.rfind("]")
                    if end != -1:
                        text = text[: end + 1]

            if not text:
                raise ValueError(
                    f"LLM returned empty text (stop_reason={message.stop_reason}). "
                    "Check API key, model config, and prompt length."
                )

            try:
                return json.loads(text)
            except json.JSONDecodeError:
                last_raw = text
                if attempt < _MAX_JSON_RETRIES:
                    continue

        raise LlmRetryExhaustedError(raw=last_raw)

    async def score_investor(
        self,
        *,
        client_name: str,
        client_thesis: str,
        client_geography: str | None,
        client_funding_target: str | None,
        investor_name: str,
        investor_notes: str | None,
        scoring_instructions: ScoringInstructions | None = None,
    ) -> LlmInvestorScore:
        notes_section = (
            f"\nPerplexity-enriched thesis context (use this to improve thesis_alignment scoring):\n{investor_notes}"
            if investor_notes
            else ""
        )
        geography_section = f"\nClient geography: {client_geography}" if client_geography else ""
        funding_section = f"\nFunding target: {client_funding_target}" if client_funding_target else ""

        profile_section = _build_profile_section(scoring_instructions)

        if scoring_instructions is not None:
            _log.debug(
                "score_investor classifier_version=%s profile=%s",
                scoring_instructions.classifier_version,
                scoring_instructions.profile_type,
            )

        payload = await self._json_call(
            system="You are a strict JSON-only scoring engine for biotech investor matching. Output ONLY valid JSON.",
            user=(
                "Score an investor against a client thesis using the 6-axis model.\n"
                f"Client: {client_name}\n"
                f"Thesis: {client_thesis}"
                f"{geography_section}"
                f"{funding_section}"
                f"\nInvestor: {investor_name}"
                f"{notes_section}\n"
                f"{profile_section}"
                "\nSCORING AXES (0-100 each):\n"
                "  thesis_alignment (30%): How well the investor's focus matches the client thesis\n"
                "  stage_fit (25%): How well the investor's typical stage matches the client\n"
                "  check_size_fit (15%): How well the investor's typical check size matches funding target\n"
                "  scientific_regulatory_fit (15%): Match on scientific/regulatory expertise; null if not applicable\n"
                "  recency (10%): How recently the investor has been active in this space\n"
                "  geography (5%): Geographic alignment between investor and client\n\n"
                "CONTENT RULES:\n"
                "- suggested_contact: If no named partner or contact is identifiable from the "
                "investor data provided, return exactly \"Not identified\". Do NOT guess a "
                "generic role or title.\n"
                "- notes: If the client thesis does NOT mention FDA, 510(k), PMA, De Novo, "
                "or clinical trials, do NOT reference any of those terms anywhere in notes, "
                "outreach_angle, or any text field — not even to say they are unnecessary. "
                "Focus only on B2B metrics: customer traction, partnerships, adoption rate, revenue.\n\n"
                "Also provide:\n"
                "  outreach_angle: A specific, actionable outreach strategy (1-2 sentences)\n"
                "  avoid: One sentence on what NOT to lead with for this investor (e.g. specific objections or known sensitivities)\n"
                "  suggested_contact: The named person to contact, or exactly \"Not identified\"\n"
                "  confidence_score: 0.0-1.0 reflecting data quality\n"
                "  evidence_urls: list of supporting URLs\n"
                "  notes: additional context or null\n"
                "  narrative_summary: 2-3 sentence plain-language summary of why this investor is or isn't a fit\n"
                "  top_claims: list of 3-5 specific human-readable evidence strings (e.g. 'Invested in 3 Series B medtech companies in 2024')\n\n"
                "Return JSON with keys: thesis_alignment, stage_fit, check_size_fit, "
                "scientific_regulatory_fit (int or null), recency, geography (0-100 ints), "
                "outreach_angle (string), avoid (string), suggested_contact (string), "
                "confidence_score (0.0-1.0), evidence_urls (list of urls), notes (string or null), "
                "narrative_summary (string), top_claims (list of 3-5 strings)."
            ),
        )

        # Determine whether to score the scientific_regulatory_fit axis.
        # If scoring_instructions explicitly enables it, always score.
        # Otherwise, fall back to needs_sci_reg() which reads FDA terms from the thesis.
        score_sci_reg = (
            scoring_instructions.score_scientific_regulatory
            if scoring_instructions is not None
            else needs_sci_reg(client_thesis)
        )

        top_claims_raw = payload.get("top_claims") or []
        return LlmInvestorScore(
            thesis_alignment=int(payload["thesis_alignment"]),
            stage_fit=int(payload["stage_fit"]),
            check_size_fit=int(payload["check_size_fit"]),
            scientific_regulatory_fit=(
                (payload.get("scientific_regulatory_fit") and int(payload["scientific_regulatory_fit"]))
                if score_sci_reg
                else None
            ),
            recency=int(payload["recency"]),
            geography=int(payload["geography"]),
            notes=payload.get("notes"),
            outreach_angle=str(payload["outreach_angle"]),
            avoid=str(payload["avoid"]) if payload.get("avoid") else None,
            suggested_contact=enforce_suggested_contact(
                str(payload["suggested_contact"]), investor_notes,
            ),
            evidence_urls=list(payload.get("evidence_urls") or []),
            confidence_score=float(payload["confidence_score"]),
            narrative_summary=str(payload.get("narrative_summary") or ""),
            top_claims=[str(c) for c in top_claims_raw[:5]],
        )

    async def analyze_signal(
        self,
        *,
        signal_type: str,
        title: str,
        url: str,
        published_at: str | None,
        raw_text: str | None,
        investor_name: str | None,
        investor_firm: str | None,
        investor_thesis_keywords: list[str] | None,
        investor_portfolio_companies: list[str] | None,
        investor_key_partners: list[str] | None,
        client_name: str | None,
        client_thesis: str | None,
        client_geography: str | None,
        client_modality: str | None,
        client_keywords: list[str] | None,
        client_stage: str | None,
        grok_batch_context: str | None,
        x_engagement_replies: int | None,
        x_engagement_reposts: int | None,
        x_engagement_likes: int | None,
        x_engagement_is_original: bool | None,
        x_engagement_author: str | None,
        x_engagement_author_type: str | None,
    ) -> LlmSignalAnalysis:
        investor_section = ""
        if investor_name:
            parts = [f"\nInvestor context: {investor_name}"]
            if investor_firm:
                parts.append(f"  Firm: {investor_firm}")
            if investor_thesis_keywords:
                parts.append(f"  Thesis keywords: {', '.join(investor_thesis_keywords)}")
            if investor_portfolio_companies:
                parts.append(f"  Portfolio: {', '.join(investor_portfolio_companies)}")
            if investor_key_partners:
                parts.append(f"  Key partners: {', '.join(investor_key_partners)}")
            investor_section = "\n".join(parts)

        client_section = ""
        if client_name:
            parts = [f"\nClient context: {client_name}"]
            if client_thesis:
                parts.append(f"  Thesis: {client_thesis}")
            if client_geography:
                parts.append(f"  Geography: {client_geography}")
            if client_stage:
                parts.append(f"  Stage: {client_stage}")
            client_section = "\n".join(parts)

        x_grok_section = ""
        x_grok_schema = ""
        if signal_type == "X_GROK":
            grok_parts = [
                "\nX POST ANALYSIS CONTEXT:",
                "Analyze this X post for investment intent signals.",
            ]
            if client_modality:
                grok_parts.append(f"  Client modality: {client_modality}")
            if client_keywords:
                grok_parts.append(f"  Keywords: {', '.join(client_keywords)}")
            if x_engagement_replies is not None:
                grok_parts.append(
                    f"  Engagement data:"
                    f"\n    Replies: {x_engagement_replies},"
                    f" Reposts: {x_engagement_reposts or 0},"
                    f" Likes: {x_engagement_likes or 0}"
                    f"\n    Is original post: {x_engagement_is_original}"
                    f"\n    Author: {x_engagement_author or 'unknown'}"
                    f"\n    Author type: {x_engagement_author_type or 'other'}"
                )
            if grok_batch_context:
                grok_parts.append(
                    f"  grok_batch_context (other posts from this search run — "
                    f"use for background context only, not as pre-scored data):\n{grok_batch_context}"
                )
            grok_parts.extend([
                "  Engagement weighting: replies > likes; "
                "is_original_post: true > false; "
                "author_type ranking: partner > firm_handle > portfolio_founder > other",
                "  Content weighting: direct match to client modality or keywords = stronger signal; "
                "adjacent vertical mention = flag but weight lower; "
                "conference mention within 7 days: priority = high, include conference name and date in briefing",
            ])
            x_grok_section = "\n".join(grok_parts)
            x_grok_schema = (
                "\n  x_signal_type: MUST be one of: thesis_statement | conference_signal | "
                "fund_activity | portfolio_mention | hiring_signal | general_activity"
            )

        payload = await self._json_call(
            system="You are a strict JSON-only signal analyst for biotech investor intelligence. Output ONLY valid JSON.",
            user=(
                "Analyze an inbound signal for priority routing and generate an actionable briefing.\n"
                f"Signal type: {signal_type}\n"
                f"Title: {title}\n"
                f"URL: {url}\n"
                f"Published: {published_at or 'unknown'}\n"
                f"Raw text: {raw_text or 'not provided'}"
                f"{investor_section}"
                f"{client_section}"
                f"{x_grok_section}\n\n"
                "Return JSON with these keys:\n"
                "  priority: HIGH|MEDIUM|LOW\n"
                "  confidence_score: 0.0-1.0\n"
                "  rationale: string explaining the priority decision\n"
                "  categories: list of category strings\n"
                "  evidence_urls: list of supporting URLs\n"
                "  relevance_score: 0-100 int\n"
                "  signal_type: MUST be one of these exact values: fund_close | fda_clearance | "
                "funding_announcement | conference | thought_leadership | partnership | exec_move | "
                "proposed_rule | draft_guidance | fda_notice | portfolio_milestone | other\n"
                "  expires_relevance: ISO date (YYYY-MM-DD) calculated from the published date "
                "using these rules: fund_close = published + 14 days, fda_clearance = published + 30 days, "
                "funding_announcement = published + 21 days, conference = published + 7 days, "
                "exec_move = published + 30 days, partnership = published + 21 days, "
                "proposed_rule/draft_guidance/fda_notice = published + 60 days, "
                "portfolio_milestone = published + 14 days, thought_leadership = published + 30 days, "
                "other = published + 14 days. If published date is unknown, use today.\n"
                "  briefing: object with keys:\n"
                "    headline: concise summary (max 300 chars)\n"
                "    why_it_matters: explanation of significance\n"
                "    outreach_angle: specific actionable outreach strategy\n"
                "    suggested_contact: best person/role to contact\n"
                "    time_sensitivity: urgency level description\n"
                "    source_urls: list of source URLs"
                f"{x_grok_schema}"
            ),
        )

        briefing_data = payload.get("briefing") or {}
        briefing = LlmSignalBriefing(
            headline=str(briefing_data.get("headline", title)),
            why_it_matters=str(briefing_data.get("why_it_matters", "")),
            outreach_angle=str(briefing_data.get("outreach_angle", "")),
            suggested_contact=enforce_suggested_contact(
                str(briefing_data.get("suggested_contact", "")),
                investor_notes=str(briefing_data.get("why_it_matters", "")),
            ),
            time_sensitivity=str(briefing_data.get("time_sensitivity", "")),
            source_urls=list(briefing_data.get("source_urls") or []),
        )

        normalized_type = normalize_signal_type(
            str(payload.get("signal_type", signal_type))
        )
        computed_expiry = compute_expiry(normalized_type, published_at)

        x_sig_type: str | None = None
        if signal_type == "X_GROK":
            raw_x = payload.get("x_signal_type")
            x_sig_type = normalize_x_signal_type(str(raw_x) if raw_x else None)

        return LlmSignalAnalysis(
            priority=normalize_priority_upper(str(payload["priority"])),
            confidence_score=float(payload["confidence_score"]),
            rationale=str(payload["rationale"]),
            categories=list(payload.get("categories") or []),
            evidence_urls=list(payload.get("evidence_urls") or []),
            relevance_score=int(payload.get("relevance_score", 50)),
            briefing=briefing,
            signal_type=normalized_type,
            expires_relevance=computed_expiry,
            x_signal_type=x_sig_type,
        )

    async def generate_digest(
        self,
        *,
        client_name: str,
        week_start: str,
        week_end: str,
        signals: list[tuple[str, str]],
        investors: list[tuple[str, str | None]],
        market_context: str | None,
        x_signals: list[dict] | None,
        therapeutic_area: str | None,
        stage: str | None,
        target_raise: str | None,
    ) -> LlmDigestResult:
        market_section = (
            f"\nReal-time market context (use for the Market Pulse section):\n{market_context}"
            if market_context
            else ""
        )
        client_context_parts = []
        if therapeutic_area:
            client_context_parts.append(f"  Therapeutic area: {therapeutic_area}")
        if stage:
            client_context_parts.append(f"  Stage: {stage}")
        if target_raise:
            client_context_parts.append(f"  Target raise: {target_raise}")
        client_context_section = (
            "\nClient context:\n" + "\n".join(client_context_parts) if client_context_parts else ""
        )

        investor_section = ""
        if investors:
            investor_lines = "\n".join(
                f"  - {name} (pipeline: {status or 'unknown'})" for name, status in investors
            )
            investor_section = (
                f"\nInvestor pipeline status (tailor outreach commentary accordingly):\n{investor_lines}"
            )

        x_section_prompt = ""
        if x_signals:
            x_lines = []
            for sig in x_signals[:20]:
                investor = sig.get("investor_name", "Unknown")
                firm = sig.get("firm", "Unknown")
                summary = sig.get("signal_summary", "")
                x_type = sig.get("x_signal_type", "general_activity")
                x_lines.append(f"  - {investor} ({firm}): {summary} [type: {x_type}]")
            x_section_prompt = (
                "\nX ACTIVITY SIGNALS (from this week):\n"
                + "\n".join(x_lines)
                + "\n\nFor the x_activity_section, produce a briefing for each signal with:"
                " investor_name, firm, signal_summary (1-2 sentences, active voice, name the person"
                " and content specifically), x_signal_type (thesis_statement|conference_signal|"
                "fund_activity|portfolio_mention|hiring_signal|general_activity),"
                " recommended_action, window (immediate|this_week|monitor),"
                " priority (high|medium|low)."
                " For conference_signal: always include conference name and date."
                " Order by window: immediate first."
                " Also include section_note summarizing the week's X activity."
            )

        x_schema_instruction = (
            "\n  x_activity_section: object with keys: section_title (string),"
            " signals (list of objects with investor_name, firm, signal_summary,"
            " x_signal_type, recommended_action, window, priority),"
            " section_note (string or null)."
            " ALWAYS include x_activity_section even if there are no X signals"
            " — in that case return signals: [] with section_note:"
            ' "No X signals recorded this week."'
        )

        internal_schema_instruction = (
            "\n\nReturn a JSON object with two top-level keys:"
            "\n1. client_digest: object with keys subject (string), preheader (string),"
            " sections (list of objects with title and bullets),"
            f" and x_activity_section.{x_schema_instruction}"
            "\n2. internal_digest: advisor preparation object with keys:"
            "\n  key_insights: list of 3-5 bullet strings summarizing the most important signals this week"
            "\n  outreach_angles: list of objects per investor with investor_name, angle (2-3 sentences: what to lead with),"
            " avoid (1 sentence: what NOT to say), re_engagement_notes (string or null — only if prior decline + new signal)"
            "\n  call_plan: object with opening_framing (~2 min framing string),"
            " discussion_threads (list of 3-5 strings), desired_outcome (string)"
            "\n  likely_objections: list of objects with objection (string) and response (string)"
            "\n  risks_sensitivities: list of strings"
            "\n  questions_to_ask: list of strings"
        )

        payload = await self._json_call(
            system="You are a strict JSON-only digest generator. Output ONLY valid JSON.",
            user=(
                "Generate a weekly investor intelligence digest for a client.\n"
                f"Client: {client_name}\n"
                f"Week: {week_start} to {week_end}"
                f"{client_context_section}"
                f"{market_section}"
                f"{investor_section}\n"
                f"Signals: {signals}"
                f"{x_section_prompt}"
                f"{internal_schema_instruction}"
            ),
        )

        client_raw = payload.get("client_digest") or payload
        sections = []
        for section in client_raw.get("sections", []):
            title = section.get("title") or section.get("section_title") or section.get("heading") or ""
            sections.append((str(title), [str(b) for b in (section.get("bullets") or [])]))

        x_section_raw = client_raw.get("x_activity_section") or {}
        x_activity_signals = []
        for sig in x_section_raw.get("signals", []):
            x_activity_signals.append(LlmXActivitySignal(
                investor_name=str(sig.get("investor_name", "Unknown")),
                firm=str(sig.get("firm", "Unknown")),
                signal_summary=str(sig.get("signal_summary", "")),
                x_signal_type=normalize_x_signal_type(sig.get("x_signal_type")) or "general_activity",
                recommended_action=str(sig.get("recommended_action", "")),
                window=normalize_window(str(sig.get("window", "monitor"))),
                priority=normalize_priority(str(sig.get("priority", "medium"))),
            ))

        x_note = x_section_raw.get("section_note")
        if not x_activity_signals and not x_note:
            x_note = "No X signals recorded this week."

        x_activity_section = LlmXActivitySection(
            signals=x_activity_signals,
            section_note=str(x_note) if x_note else None,
        )

        advisor_raw = payload.get("internal_digest") or {}
        advisor_prep = self._parse_advisor_prep(advisor_raw)

        return LlmDigestResult(
            subject=str(client_raw.get("subject", "")),
            preheader=str(client_raw.get("preheader", "")),
            sections=sections,
            x_activity_section=x_activity_section,
            advisor_prep=advisor_prep,
        )

    def _parse_advisor_prep(self, raw: dict) -> LlmAdvisorPrep:
        angles = []
        for a in raw.get("outreach_angles") or []:
            angles.append(LlmAdvisorOutreachAngle(
                investor_name=str(a.get("investor_name", "")),
                angle=str(a.get("angle", "")),
                avoid=str(a.get("avoid", "")),
                re_engagement_notes=a.get("re_engagement_notes"),
            ))

        call_raw = raw.get("call_plan") or {}
        call_plan = LlmAdvisorCallPlan(
            opening_framing=str(call_raw.get("opening_framing", "")),
            discussion_threads=[str(t) for t in (call_raw.get("discussion_threads") or [])],
            desired_outcome=str(call_raw.get("desired_outcome", "")),
        )

        objections = []
        for o in raw.get("likely_objections") or []:
            objections.append(LlmAdvisorObjection(
                objection=str(o.get("objection", "")),
                response=str(o.get("response", "")),
            ))

        return LlmAdvisorPrep(
            key_insights=[str(i) for i in (raw.get("key_insights") or [])],
            outreach_angles=angles,
            call_plan=call_plan,
            likely_objections=objections,
            risks_sensitivities=[str(r) for r in (raw.get("risks_sensitivities") or [])],
            questions_to_ask=[str(q) for q in (raw.get("questions_to_ask") or [])],
        )

    async def score_grant(
        self,
        *,
        company_name: str,
        therapeutic_area: str,
        stage: str,
        fda_pathway: str | None,
        keywords: list[str],
        grant_title: str,
        grant_agency: str,
        grant_program: str | None,
        grant_description: str | None,
        grant_eligibility: str | None,
        grant_award_amount: str | None,
        grant_deadline: str | None,
    ) -> LlmGrantScore:
        payload = await self._json_call(
            system="You are a strict JSON-only grant scoring engine for life sciences companies. Output ONLY valid JSON.",
            user=(
                "Score a federal grant opportunity against a client profile.\n\n"
                "CLIENT PROFILE:\n"
                f"  Company: {company_name}\n"
                f"  Therapeutic area: {therapeutic_area}\n"
                f"  Stage: {stage}\n"
                f"  FDA pathway: {fda_pathway or 'not specified'}\n"
                f"  Keywords: {', '.join(keywords)}\n\n"
                "GRANT OPPORTUNITY:\n"
                f"  Title: {grant_title}\n"
                f"  Agency: {grant_agency}\n"
                f"  Program: {grant_program or 'not specified'}\n"
                f"  Award amount: {grant_award_amount or 'not specified'}\n"
                f"  Deadline: {grant_deadline or 'not specified'}\n"
                f"  Description: {grant_description or 'not provided'}\n"
                f"  Eligibility: {grant_eligibility or 'not provided'}\n\n"
                "Scoring weights: therapeutic_match 35%, stage_eligibility 25%, "
                "award_size_relevance 15%, deadline_feasibility 15%, historical_funding 10%.\n\n"
                "If grant description is vague or eligibility criteria are unclear, set confidence to 'low'. "
                "Do not fabricate eligibility assessments.\n\n"
                "Return JSON with keys: overall_score (0-100 int), "
                "therapeutic_match (0-100 int), stage_eligibility (0-100 int), "
                "award_size_relevance (0-100 int), deadline_feasibility (0-100 int), "
                "historical_funding (0-100 int), rationale (string), "
                "application_guidance (string or null), confidence ('high'|'medium'|'low')."
            ),
        )

        return LlmGrantScore(
            overall_score=int(payload["overall_score"]),
            therapeutic_match=int(payload["therapeutic_match"]),
            stage_eligibility=int(payload["stage_eligibility"]),
            award_size_relevance=int(payload["award_size_relevance"]),
            deadline_feasibility=int(payload["deadline_feasibility"]),
            historical_funding=int(payload["historical_funding"]),
            rationale=str(payload["rationale"]),
            application_guidance=payload.get("application_guidance"),
            confidence=str(payload["confidence"]),
        )
