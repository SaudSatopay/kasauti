"""Reverse-image verification via SerpApi's Google Lens engine.

The single most common misinformation pattern in Indian WhatsApp groups is a
*real* photo recycled with a *false* caption — a 2019 flood presented as
yesterday's, a foreign incident relocated to an Indian city. Lens tells us
where else the image appears; any dated appearances let us build an
"earliest known appearance" timeline that exposes recycling instantly.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Optional

from .evidence import parse_date
from .models import EvidenceItem, ImageAnalysis, ImageMatch
from .sources import classify_domain, domain_of

_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


def _title_year_hint(matches: list[ImageMatch]) -> Optional[int]:
    """Years that match *titles* keep mentioning are a strong era signal even
    when Lens returns no dates ('2004 Indian Ocean tsunami - Wikipedia')."""
    years = [int(y) for m in matches for y in _YEAR_RE.findall(m.title or "")]
    if not years:
        return None
    counts = Counter(years)
    year, _n = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    return year


def analyze_lens(image_url: str, raw: dict[str, Any]) -> ImageAnalysis:
    matches: list[ImageMatch] = []
    for item in (raw.get("visual_matches") or [])[:20]:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        matches.append(ImageMatch(
            title=item.get("title"),
            link=link,
            domain=domain_of(link) if link else None,
            source=item.get("source"),
            date_raw=item.get("date"),
            date=parse_date(item.get("date")),
            thumbnail=item.get("thumbnail"),
        ))

    dated = [m for m in matches if m.date is not None]
    earliest = min(dated, key=lambda m: m.date) if dated else None  # type: ignore[arg-type]
    domains = {m.domain for m in matches if m.domain}
    year_hint = _title_year_hint(matches)

    note: Optional[str] = None
    if earliest and earliest.date:
        note = (
            f"This image already appears on {len(matches)} other pages; the earliest "
            f"dated appearance is {earliest.date.date().isoformat()} on "
            f"{earliest.domain or 'an unknown site'}. If the forward presents it as a "
            f"current event, that date is the tell."
        )
    elif matches and year_hint:
        note = (
            f"This image appears on {len(matches)} other pages across "
            f"{len(domains)} sites. None carried a machine-readable date, but the "
            f"match titles repeatedly reference {year_hint} — likely the image's "
            f"true era, not today."
        )
    elif matches:
        note = (
            f"This image appears on {len(matches)} other pages across "
            f"{len(domains)} sites. None carried a machine-readable date, but the "
            f"matches below show its real contexts."
        )
    else:
        note = (
            "Google Lens found no other appearances of this image. That neither "
            "confirms nor debunks it — it may be original, private, or AI-generated."
        )

    return ImageAnalysis(
        image_url=image_url,
        matches=matches,
        distinct_domains=len(domains),
        earliest_date=earliest.date if earliest else None,
        earliest_domain=earliest.domain if earliest else None,
        title_year_hint=year_hint,
        note=note,
    )


def lens_evidence(analysis: ImageAnalysis, *, start_index: int, max_items: int = 5
                  ) -> list[EvidenceItem]:
    """Convert the most credible Lens matches into citable evidence items."""
    scored: list[tuple[float, ImageMatch]] = []
    for m in analysis.matches:
        if not m.link or not m.domain:
            continue
        cred = classify_domain(m.domain)
        bonus = 0.15 if m.date else 0.0
        scored.append((cred.weight + bonus, m))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    items: list[EvidenceItem] = []
    for offset, (_, m) in enumerate(scored[:max_items]):
        cred = classify_domain(m.domain or "")
        items.append(EvidenceItem(
            id=f"E{start_index + offset}",
            claim_id=None,
            channel="lens",
            title=m.title or f"Image match on {m.domain}",
            link=m.link or "",
            domain=m.domain or "",
            source_name=m.source,
            snippet=None,
            date_raw=m.date_raw,
            date=m.date,
            credibility=cred,
            score=round(cred.weight, 4),
        ))
    return items
