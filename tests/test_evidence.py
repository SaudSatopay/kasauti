from datetime import datetime, timedelta, timezone

from kasauti.evidence import build_evidence, normalize_news, normalize_web, parse_date, relevance
from kasauti.models import Claim, SourceTier


def _claim() -> Claim:
    return Claim(
        id="C1",
        text_en="UNESCO declared the Indian national anthem the best in the world",
        queries=["UNESCO Indian national anthem best"],
    )


def test_parse_relative_dates():
    now = datetime.now(timezone.utc)
    d = parse_date("2 days ago")
    assert d is not None and (now - d) - timedelta(days=2) < timedelta(minutes=5)
    assert parse_date("3 hours ago") is not None
    assert parse_date("yesterday") is not None


def test_parse_absolute_dates():
    assert parse_date("Sep 12, 2026").date().isoformat() == "2026-09-12"
    assert parse_date("12 Sep 2026").date().isoformat() == "2026-09-12"
    assert parse_date("2026-09-12").date().isoformat() == "2026-09-12"


def test_parse_google_news_format():
    d = parse_date("09/16/2026, 07:00 AM, +0000 UTC")
    assert d is not None and d.date().isoformat() == "2026-09-16"


def test_parse_garbage_returns_none():
    assert parse_date(None) is None
    assert parse_date("") is None
    assert parse_date("sometime soon") is None


def test_relevance_overlap():
    high = relevance("UNESCO anthem award", "UNESCO has not given any anthem award", "")
    low = relevance("UNESCO anthem award", "Cricket scores today", "IPL update")
    assert high > low
    assert low == 0.0


def test_normalize_web_and_dedupe_and_rank():
    raw = {
        "organic_results": [
            {
                "title": "No, UNESCO has not declared the Indian anthem best",
                "link": "https://www.altnews.in/unesco-anthem/",
                "snippet": "UNESCO gives no such anthem award; the viral claim is false.",
                "date": "Aug 14, 2024",
            },
            {   # exact duplicate link with tracking params → deduped
                "title": "No, UNESCO has not declared the Indian anthem best",
                "link": "https://www.altnews.in/unesco-anthem/?utm_source=x",
                "snippet": "dupe",
            },
            {
                "title": "UNESCO anthem best declared proud moment India",
                "link": "https://random-viral-blog.xyz/unesco",
                "snippet": "Proud moment! UNESCO declared Indian anthem best in the world!",
            },
        ]
    }
    items = build_evidence(_claim(), [normalize_web(raw)])
    assert len(items) == 2  # dupe removed
    # Fact-checker must outrank the unknown blog despite the blog's high overlap.
    assert items[0].domain == "altnews.in"
    assert items[0].credibility.tier == SourceTier.FACT_CHECKER
    assert items[0].id == "E1"
    assert items[1].id == "E2"


def test_normalize_news_flattens_nested_stories():
    raw = {
        "news_results": [
            {
                "title": "cluster",
                "stories": [
                    {
                        "title": "Anthem hoax resurfaces",
                        "link": "https://indianexpress.com/a",
                        "source": {"name": "The Indian Express"},
                        "date": "08/14/2025, 07:00 AM, +0000 UTC",
                    }
                ],
            },
            {
                "title": "Direct item",
                "link": "https://ndtv.com/b",
                "source": {"name": "NDTV"},
            },
        ]
    }
    flat = normalize_news(raw)
    assert len(flat) == 2
    assert flat[0]["source_name"] == "The Indian Express"


def test_listing_pages_filtered_out():
    raw = {
        "organic_results": [
            {   # category archive on a fact-check domain — junk, must be dropped
                "title": "English Archives - Page 662 of 664",
                "link": "https://factly.in/category/english/page/662/",
                "snippet": "UNESCO anthem and other fact checks",
            },
            {
                "title": "UNESCO anthem claim: our fact check",
                "link": "https://factly.in/unesco-anthem-claim-fact-check/",
                "snippet": "UNESCO declared anthem best claim reviewed",
            },
            {
                "title": "Anthem coverage",
                "link": "https://example.com/tag/anthem/",
                "snippet": "all anthem stories",
            },
        ]
    }
    items = build_evidence(_claim(), [normalize_web(raw)])
    links = [e.link for e in items]
    assert links == ["https://factly.in/unesco-anthem-claim-fact-check/"]


def test_evidence_ids_offset():
    raw = {"organic_results": [{"title": "UNESCO anthem claim checked",
                                "link": "https://factly.in/x", "snippet": "anthem"}]}
    items = build_evidence(_claim(), [normalize_web(raw)], start_index=7)
    assert items[0].id == "E7"
