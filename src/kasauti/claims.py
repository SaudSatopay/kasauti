"""Claim extraction — turn a messy forward into atomic, searchable claims.

With an LLM: handles Hindi / Hinglish / regional languages, splits compound
messages into separate checkable claims, and drafts diverse search queries.

Without an LLM: falls back to cleaning the raw text and searching it directly.
Less precise, but the pipeline still runs end-to-end on a SerpApi key alone.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from .llm import LLM
from .models import Claim, ClaimExtraction

HARD_MAX_CLAIMS = 4

_SYSTEM = """You are the claim-extraction module of Kasauti, a misinformation checker for India.
You receive raw WhatsApp-forward text: possibly Hindi, Hinglish, English or a regional Indian
language, full of emojis and formatting noise.

Return ONLY a JSON object:
{
  "language": "<BCP-47 code of the dominant language, e.g. en, hi, hi-Latn, ta, te>",
  "language_name": "<human name, e.g. Hinglish>",
  "translation_en": "<faithful English translation of the whole message, or null if already English>",
  "summary": "<one neutral sentence: what does this forward want the reader to believe?>",
  "claims": [
    {
      "text_en": "<one atomic, verifiable factual claim, in clear English>",
      "original_excerpt": "<the fragment of the original message this claim comes from>",
      "kind": "<event|statistic|health|scheme|job|quote|image_context|other>",
      "queries": ["<news-style search query>", "<entity/keyword query, different angle>"]
    }
  ]
}

Rules:
- Extract at most {max_claims} claims, ordered by how central they are to the message.
- A claim must be checkable against public reporting (who/what/when/where). Skip pure opinions,
  greetings, blessings and forwarding pleas.
- Queries must be in English, concrete, and MUST NOT contain the words "fact check"
  (a separate module handles fact-check sites).
- If the message references an attached image (e.g. "this photo shows..."), add a claim of
  kind "image_context" describing what the image allegedly shows.
- If there is genuinely nothing checkable, return an empty claims list."""

_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")
_FORWARD_NOISE = re.compile(
    r"(forwarded as received|forwarded many times|\*|_|~)", re.IGNORECASE
)


def _clean(text: str) -> str:
    text = _URL_RE.sub(" ", text or "")
    text = _FORWARD_NOISE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def max_claims_setting() -> int:
    try:
        value = int(os.getenv("KASAUTI_MAX_CLAIMS", "2"))
    except ValueError:
        value = 2
    return max(1, min(HARD_MAX_CLAIMS, value))


def _fallback(text: str, image_url: Optional[str]) -> ClaimExtraction:
    cleaned = _clean(text)
    claims: list[Claim] = []
    if cleaned:
        head = cleaned[:180]
        claims.append(
            Claim(
                id="C1",
                text_en=head,
                original_excerpt=head,
                kind="other",
                queries=[head[:100], f"{head[:80]} India news"],
            )
        )
    if image_url and not claims:
        claims.append(
            Claim(
                id="C1",
                text_en="Context of the attached image",
                kind="image_context",
                queries=[],
            )
        )
    return ClaimExtraction(
        language="und",
        language_name="Unknown (rule-based mode)",
        translation_en=None,
        summary=None,
        claims=claims,
        llm_used=False,
    )


IMAGE_CLAIM_TEXT = (
    "The attached photo is a genuine, current image of the event described in "
    "the message (not an older or unrelated photo)."
)


def _ensure_image_claim(extraction: ClaimExtraction, image_url: Optional[str]) -> ClaimExtraction:
    """A forward with a photo always carries one more claim: that the photo
    shows what the text says it shows. It is judged on Google Lens evidence
    alone (no text searches), so a true caption on a recycled photo still
    yields OUTDATED — the single most common WhatsApp lie format."""
    if image_url and not any(c.kind == "image_context" for c in extraction.claims):
        extraction.claims.append(Claim(
            id=f"C{len(extraction.claims) + 1}",
            text_en=IMAGE_CLAIM_TEXT,
            kind="image_context",
            queries=[],
        ))
    return extraction


def extract_claims(
    text: str, image_url: Optional[str] = None, llm: Optional[LLM] = None
) -> ClaimExtraction:
    return _ensure_image_claim(_extract_claims(text, image_url, llm), image_url)


def _extract_claims(
    text: str, image_url: Optional[str] = None, llm: Optional[LLM] = None
) -> ClaimExtraction:
    llm = llm or LLM()
    limit = max_claims_setting()
    if not llm.available:
        return _fallback(text, image_url)

    user = text.strip()
    if image_url:
        user += "\n\n[An image is attached to this forward.]"
    data = llm.chat_json(_SYSTEM.replace("{max_claims}", str(limit)), user)
    if not data:
        return _fallback(text, image_url)

    claims: list[Claim] = []
    for i, c in enumerate((data.get("claims") or [])[:limit], start=1):
        if not isinstance(c, dict):
            continue
        text_en = str(c.get("text_en") or "").strip()
        if not text_en:
            continue
        queries = [str(q).strip() for q in (c.get("queries") or []) if str(q).strip()]
        # Belt & braces: strip any fact-check phrasing the model slipped in.
        queries = [re.sub(r"\bfact[- ]?check(ed|ing)?\b", "", q, flags=re.I).strip() for q in queries]
        queries = [q for q in queries if q][:2] or [text_en[:100]]
        claims.append(
            Claim(
                id=f"C{i}",
                text_en=text_en,
                original_excerpt=(str(c.get("original_excerpt") or "").strip() or None),
                kind=str(c.get("kind") or "other").strip() or "other",
                queries=queries,
            )
        )
    if not claims:
        return _fallback(text, image_url)

    return ClaimExtraction(
        language=str(data.get("language") or "en"),
        language_name=str(data.get("language_name") or "English"),
        translation_en=(str(data.get("translation_en")).strip()
                        if data.get("translation_en") else None),
        summary=(str(data.get("summary")).strip() if data.get("summary") else None),
        claims=claims,
        llm_used=True,
    )
