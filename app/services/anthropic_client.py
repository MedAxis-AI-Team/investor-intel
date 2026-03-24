from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from app.config import Settings
from app.services.llm_client import (
    LlmClient,
    LlmDigestResult,
    LlmGrantScore,
    LlmInvestorScore,
    LlmSignalAnalysis,
    LlmSignalBriefing,
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
            scientific_regulatory_fit=payload.get("scientific_regulatory_fit") and int(payload["scientific_regulatory_fit"]),
            recency=int(payload["recency"]),
            geography=int(payload["geography"]),
            notes=payload.get("notes"),
            outreach_angle=str(payload["outreach_angle"]),
            suggested_contact=str(payload["suggested_contact"]),
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
        investor_thesis_keywords: list[str] | None,
        investor_portfolio_companies: list[str] | None,
        investor_key_partners: list[str] | None,
        client_name: str | None,
        client_thesis: str | None,
        client_geography: str | None,
    ) -> LlmSignalAnalysis:
        investor_section = ""
        if investor_name:
            parts = [f"\nInvestor context: {investor_name}"]
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
            client_section = "\n".join(parts)

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
                f"{client_section}\n\n"
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

        return LlmSignalAnalysis(
            priority=str(payload["priority"]),
            confidence_score=float(payload["confidence_score"]),
            rationale=str(payload["rationale"]),
            categories=list(payload.get("categories") or []),
            evidence_urls=list(payload.get("evidence_urls") or []),
            relevance_score=int(payload.get("relevance_score", 50)),
            briefing=briefing,
            signal_type=str(payload.get("signal_type", signal_type)),
            expires_relevance=str(payload.get("expires_relevance", "")),
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

        payload = await self._json_call(
            system="You are a strict JSON-only digest generator. Output ONLY valid JSON.",
            user=(
                "Generate a weekly digest for a client.\n"
                f"Client: {client_name}\n"
                f"Week: {week_start} to {week_end}"
                f"{market_section}"
                f"{investor_section}\n"
                f"Signals: {signals}\n\n"
                "Return JSON with keys: subject (string), preheader (string), sections (list of objects with title and bullets)."
            ),
        )

        sections = []
        for section in payload["sections"]:
            sections.append((str(section["title"]), [str(b) for b in (section.get("bullets") or [])]))

        return LlmDigestResult(
            subject=str(payload["subject"]),
            preheader=str(payload["preheader"]),
            sections=sections,
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
