from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from app.config import Settings
from app.services.llm_client import LlmClient, LlmDigestResult, LlmInvestorScore, LlmSignalAnalysis


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

        return json.loads(text)

    async def score_investor(self, *, client_name: str, client_thesis: str, investor_name: str) -> LlmInvestorScore:
        payload = await self._json_call(
            system="You are a strict JSON-only scoring engine. Output ONLY valid JSON.",
            user=(
                "Score an investor against a client thesis.\n"
                f"Client: {client_name}\n"
                f"Thesis: {client_thesis}\n"
                f"Investor: {investor_name}\n\n"
                "Return JSON with keys: thesis_alignment, stage_fit, check_size_fit, strategic_value (0-100 ints), "
                "confidence_score (0.0-1.0), evidence_urls (list of urls), notes (string or null)."
            ),
        )

        return LlmInvestorScore(
            thesis_alignment=int(payload["thesis_alignment"]),
            stage_fit=int(payload["stage_fit"]),
            check_size_fit=int(payload["check_size_fit"]),
            strategic_value=int(payload["strategic_value"]),
            confidence_score=float(payload["confidence_score"]),
            evidence_urls=list(payload.get("evidence_urls") or []),
            notes=payload.get("notes"),
        )

    async def analyze_signal(self, *, signal_type: str, title: str, url: str, raw_text: str | None) -> LlmSignalAnalysis:
        payload = await self._json_call(
            system="You are a strict JSON-only analyst. Output ONLY valid JSON.",
            user=(
                "Analyze an inbound signal for priority routing.\n"
                f"Signal type: {signal_type}\n"
                f"Title: {title}\n"
                f"URL: {url}\n"
                f"Raw text (optional): {raw_text or ''}\n\n"
                "Return JSON with keys: priority (HIGH|MEDIUM|LOW), confidence_score (0.0-1.0), "
                "rationale (string), categories (list of strings), evidence_urls (list of urls)."
            ),
        )

        return LlmSignalAnalysis(
            priority=str(payload["priority"]),
            confidence_score=float(payload["confidence_score"]),
            rationale=str(payload["rationale"]),
            categories=list(payload.get("categories") or []),
            evidence_urls=list(payload.get("evidence_urls") or []),
        )

    async def generate_digest(
        self, *, client_name: str, week_start: str, week_end: str, signals: list[tuple[str, str]]
    ) -> LlmDigestResult:
        payload = await self._json_call(
            system="You are a strict JSON-only digest generator. Output ONLY valid JSON.",
            user=(
                "Generate a weekly digest for a client.\n"
                f"Client: {client_name}\n"
                f"Week: {week_start} to {week_end}\n"
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
