"""Evidence normalisation, deduplication and credibility-weighted ranking."""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from .models import Claim, EvidenceItem, SourceTier
from .sources import classify_domain, domain_of

_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is",
    "are", "was", "were", "has", "have", "had", "will", "would", "that", "this",
    "with", "by", "from", "as", "it", "its", "be", "been", "not", "no", "new",
    "india", "indian", "news", "says", "said",
}

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
)}

_REL_RE = re.compile(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", re.I)


def parse_date(raw: Optional[str]) -> Optional[datetime]:
    """Parse the date formats SerpApi engines actually emit.

    Seen in the wild: '2 days ago', 'Sep 12, 2026', '12 Sep 2026',
    '09/16/2026, 07:00 AM, +0000 UTC' (google_news), ISO dates, 'yesterday'.
    """
    if not raw:
        return None
    text = raw.strip()
    now = datetime.now(timezone.utc)

    m = _REL_RE.search(text)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
            "year": timedelta(days=365 * n),
        }[unit]
        return now - delta
    if text.lower() == "yesterday":
        return now - timedelta(days=1)

    # google_news: '09/16/2026, 07:00 AM, +0000 UTC'
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", text)
    if m:
        mm, dd, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(yyyy, mm, dd, tzinfo=timezone.utc)
        except ValueError:
            return None

    # 'Sep 12, 2026' / '12 Sep 2026' / 'September 12, 2026'
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", text)
    if m and m.group(1)[:3].lower() in _MONTHS:
        try:
            return datetime(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()],
                            int(m.group(2)), tzinfo=timezone.utc)
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", text)
    if m and m.group(2)[:3].lower() in _MONTHS:
        try:
            return datetime(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()],
                            int(m.group(1)), tzinfo=timezone.utc)
        except ValueError:
            return None

    # ISO-ish
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


def relevance(claim_text: str, title: str, snippet: Optional[str]) -> float:
    """Token-overlap relevance in [0, 1] between a claim and a result."""
    claim_tokens = _tokens(claim_text)
    result_tokens = _tokens(f"{title} {snippet or ''}")
    if not claim_tokens or not result_tokens:
        return 0.0
    return len(claim_tokens & result_tokens) / len(claim_tokens)


def _recency_factor(date: Optional[datetime], tier: SourceTier) -> float:
    # A three-year-old fact-check of a recycled hoax is still decisive
    # evidence, so authoritative tiers are never punished for age.
    if tier in (SourceTier.FACT_CHECKER, SourceTier.OFFICIAL):
        return 1.0
    if date is None:
        return 0.85
    age = datetime.now(timezone.utc) - date
    if age <= timedelta(days=7):
        return 1.0
    if age <= timedelta(days=30):
        return 0.92
    if age <= timedelta(days=365):
        return 0.82
    return 0.72


def normalize_web(raw: dict[str, Any], *, channel: str = "web") -> list[dict[str, Any]]:
    """Flatten `google` engine output (organic_results) into plain dicts."""
    out: list[dict[str, Any]] = []
    for item in raw.get("organic_results", []) or []:
        link = item.get("link") or ""
        if not link:
            continue
        out.append({
            "channel": channel,
            "title": item.get("title") or link,
            "link": link,
            "snippet": item.get("snippet"),
            "date_raw": item.get("date"),
            "source_name": item.get("source"),
            "favicon": item.get("favicon"),
        })
    return out


def normalize_news(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten `google_news` output (news_results, including nested stories)."""
    out: list[dict[str, Any]] = []

    def push(item: dict[str, Any]) -> None:
        link = item.get("link") or ""
        if not link:
            return
        source = item.get("source")
        source_name = source.get("name") if isinstance(source, dict) else source
        out.append({
            "channel": "news",
            "title": item.get("title") or link,
            "link": link,
            "snippet": item.get("snippet"),
            "date_raw": item.get("date"),
            "source_name": source_name,
            "favicon": (source or {}).get("icon") if isinstance(source, dict) else None,
        })

    for item in raw.get("news_results", []) or []:
        if isinstance(item, dict) and isinstance(item.get("stories"), list):
            for story in item["stories"]:
                if isinstance(story, dict):
                    push(story)
        elif isinstance(item, dict):
            push(item)
    return out


def _canonical_link(link: str) -> str:
    link = re.sub(r"[?#].*$", "", link.strip().lower())
    return link.rstrip("/")


def build_evidence(
    claim: Claim,
    raw_batches: Iterable[list[dict[str, Any]]],
    *,
    start_index: int = 1,
    max_items: int = 10,
) -> list[EvidenceItem]:
    """Merge, dedupe, classify and rank raw results for one claim."""
    merged: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    for batch in raw_batches:
        for item in batch:
            canon = _canonical_link(item["link"])
            if canon in seen_links:
                continue
            seen_links.add(canon)
            merged.append(item)

    # Fuzzy near-duplicate titles on the same domain (syndicated copies).
    kept: list[dict[str, Any]] = []
    for item in merged:
        dom = domain_of(item["link"])
        duplicate = False
        for other in kept:
            if domain_of(other["link"]) != dom:
                continue
            ratio = difflib.SequenceMatcher(
                None, item["title"].lower(), other["title"].lower()
            ).ratio()
            if ratio > 0.9:
                duplicate = True
                break
        if not duplicate:
            item["_domain"] = dom
            kept.append(item)

    items: list[EvidenceItem] = []
    for raw in kept:
        cred = classify_domain(raw["_domain"])
        date = parse_date(raw.get("date_raw"))
        rel = relevance(claim.text_en, raw["title"], raw.get("snippet"))
        score = cred.weight * (0.45 + 0.55 * rel) * _recency_factor(date, cred.tier)
        # A fact-check desk directly covering the claim is the strongest
        # signal we can get; make sure it can't be outranked by volume.
        if cred.tier == SourceTier.FACT_CHECKER and rel > 0.25:
            score += 0.25
        items.append(EvidenceItem(
            id="pending",
            claim_id=claim.id,
            channel=raw["channel"],
            title=raw["title"],
            link=raw["link"],
            domain=raw["_domain"],
            source_name=raw.get("source_name"),
            snippet=raw.get("snippet"),
            date_raw=raw.get("date_raw"),
            date=date,
            credibility=cred,
            score=round(score, 4),
            favicon=raw.get("favicon"),
        ))

    items.sort(key=lambda e: e.score, reverse=True)
    items = items[:max_items]
    for offset, item in enumerate(items):
        item.id = f"E{start_index + offset}"
    return items
