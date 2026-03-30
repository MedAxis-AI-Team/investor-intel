from __future__ import annotations

import json

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
    LlmClient,
    LlmDigestResult,
    LlmGrantScore,
    LlmInvestorScore,
    LlmSignalAnalysis,
    LlmSignalBriefing,
    LlmXActivitySection,
    LlmXActivitySignal,
)


class AnthropicLlmClient(LlmClient):
    def __init__(self, *, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=settings.request_timeout_seconds)
        self._model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens

    async def _json_call(self, *, system: str, user: str) -> dict:
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        text = ""
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text += block.text

        # Strip markdown code fences if the LLM wrapped its JSON output
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
            text = text.strip()

        if not text:
            raise ValueError(
                f"LLM returned empty text (stop_reason={message.stop_reason}). "
                "Check API key, model config, and prompt length."
            )

        return json.loads(text)

    async def score_investor(
        self,
        *,
        client_name: str,
        client_thesis: str,
        client_geography: str | None,
        client_funding_target: str | None,
        investor_name: str,
        investor_notes: str | None,
    ) -> LlmInvestorScore:
        notes_section = (
            f"\nPerplexity-enriched thesis context (use this to improve thesis_alignment scoring):\n{investor_notes}"
            if investor_notes
            else ""
        )
        geography_section = f"\nClient geography: {client_geography}" if client_geography else ""
        funding_section = f"\nFunding target: {client_funding_target}" if client_funding_target else ""

        payload = await self._json_call(
            system="You are a strict JSON-only scoring engine for biotech investor matching. Output ONLY valid JSON.",
            user=(
                "Score an investor against a client thesis using the 6-axis model.\n"
                f"Client: {client_name}\n"
                f"Thesis: {client_thesis}"
                f"{geography_section}"
                f"{funding_section}"
                f"\nInvestor: {investor_name}"
                f"{notes_section}\n\n"
                "SCORING AXES (0-100 each):\n"
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
                "  suggested_contact: The named person to contact, or exactly \"Not identified\"\n"
                "  confidence_score: 0.0-1.0 reflecting data quality\n"
                "  evidence_urls: list of supporting URLs\n"
                "  notes: additional context or null\n\n"
                "Return JSON with keys: thesis_alignment, stage_fit, check_size_fit, "
                "scientific_regulatory_fit (int or null), recency, geography (0-100 ints), "
                "outreach_angle (string), suggested_contact (string), "
                "confidence_score (0.0-1.0), evidence_urls (list of urls), notes (string or null)."
            ),
        )

        return LlmInvestorScore(
            thesis_alignment=int(payload["thesis_alignment"]),
            stage_fit=int(payload["stage_fit"]),
            check_size_fit=int(payload["check_size_fit"]),
            scientific_regulatory_fit=(
                (payload.get("scientific_regulatory_fit") and int(payload["scientific_regulatory_fit"]))
                if needs_sci_reg(client_thesis)
                else None
            ),
            recency=int(payload["recency"]),
            geography=int(payload["geography"]),
            notes=payload.get("notes"),
            outreach_angle=str(payload["outreach_angle"]),
            suggested_contact=enforce_suggested_contact(
                str(payload["suggested_contact"]), investor_notes,
            ),
            evidence_urls=list(payload.get("evidence_urls") or []),
            confidence_score=float(payload["confidence_score"]),
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
            suggested_contact=str(briefing_data.get("suggested_contact", "")),
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
    ) -> LlmDigestResult:
        market_section = (
            f"\nReal-time market context (use for the Market Pulse section):\n{market_context}"
            if market_context
            else ""
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

        payload = await self._json_call(
            system="You are a strict JSON-only digest generator. Output ONLY valid JSON.",
            user=(
                "Generate a weekly digest for a client.\n"
                f"Client: {client_name}\n"
                f"Week: {week_start} to {week_end}"
                f"{market_section}"
                f"{investor_section}\n"
                f"Signals: {signals}"
                f"{x_section_prompt}\n\n"
                "Return JSON with keys: subject (string), preheader (string),"
                " sections (list of objects with title and bullets)."
                f"{x_schema_instruction}"
            ),
        )

        sections = []
        for section in payload["sections"]:
            sections.append((str(section["title"]), [str(b) for b in (section.get("bullets") or [])]))

        x_section_raw = payload.get("x_activity_section") or {}
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

        return LlmDigestResult(
            subject=str(payload["subject"]),
            preheader=str(payload["preheader"]),
            sections=sections,
            x_activity_section=x_activity_section,
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
