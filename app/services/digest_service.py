from __future__ import annotations

import html

from app.models.generate_digest import (
    DigestPayload,
    DigestSection,
    GenerateDigestRequest,
    GenerateDigestResponse,
)
from app.services.llm_client import LlmClient


def _render_html(*, payload: DigestPayload) -> str:
    safe_subject = html.escape(payload.subject)
    sections_html = []
    for section in payload.sections:
        bullets_html = "".join(f"<li>{html.escape(b)}</li>" for b in section.bullets)
        sections_html.append(f"<h2>{html.escape(section.title)}</h2><ul>{bullets_html}</ul>")

    body = "".join(sections_html)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{safe_subject}</title></head><body>{body}</body></html>"


class DigestService:
    def __init__(self, *, llm: LlmClient) -> None:
        self._llm = llm

    async def generate(self, req: GenerateDigestRequest) -> GenerateDigestResponse:
        llm_result = await self._llm.generate_digest(
            client_name=req.client.name,
            week_start=req.week_start,
            week_end=req.week_end,
            signals=[(s.title, s.url) for s in req.signals],
        )

        sections = [DigestSection(title=title, bullets=bullets) for (title, bullets) in llm_result.sections]
        payload = DigestPayload(subject=llm_result.subject, preheader=llm_result.preheader, sections=sections)
        html_body = _render_html(payload=payload)

        return GenerateDigestResponse(html=html_body, payload=payload)
