"""End-to-end pipeline tests: offline fixtures, no LLM, zero network."""
from kasauti import check
from kasauti.models import SourceTier, VerdictLabel
from kasauti.serp import SerpSearcher

UNESCO = (
    "Good news!! 🇮🇳 UNESCO has declared our JANA GANA MANA the BEST NATIONAL "
    "ANTHEM in the world!! Forward this to every Indian!!"
)

TSUNAMI_IMAGE = (
    "https://upload.wikimedia.org/wikipedia/commons/8/80/"
    "US_Navy_050102-N-9593M-040_A_village_near_the_coast_of_Sumatra_lays_in_"
    "ruin_after_the_Tsunami_that_struck_South_East_Asia.jpg"
)


def test_unesco_hoax_end_to_end():
    events: list[tuple[str, str]] = []
    report = check(UNESCO, on_event=lambda s, d: events.append((s, d)))

    # Fingerprint caught the chain-forward markers.
    assert report.fingerprint.score >= 25

    # Fixtures produced evidence, with fact-checkers ranked on top.
    assert report.evidence, "expected evidence from bundled fixtures"
    assert report.evidence[0].credibility.tier == SourceTier.FACT_CHECKER

    # Rule-based mode reads debunk headlines from fact-check desks → false.
    assert report.overall_label == VerdictLabel.FALSE

    # A reply was drafted even without an LLM.
    assert report.suggested_reply
    assert "http" in report.suggested_reply

    # Budget accounting: 1 claim × 3 strategies.
    assert report.searches_used == 3
    assert report.offline is True
    assert report.llm_used is False

    # Progress events cover the pipeline stages in order.
    stages = [s for s, _ in events]
    for stage in ("fingerprint", "claims", "search", "evidence", "verdicts", "done"):
        assert stage in stages


def test_image_check_detects_recycled_photo():
    report = check(
        "CYCLONE ALERT! Massive destruction on the Tamil Nadu coast right now! "
        "Share before it gets deleted!",
        image_url=TSUNAMI_IMAGE,
    )
    assert report.image is not None
    assert report.image.matches, "lens fixture should produce matches"
    # Lens matches carry no machine-readable dates for this image, but the
    # match titles keep saying 2004 — the title-year heuristic catches it.
    assert report.image.earliest_date is None
    assert report.image.title_year_hint == 2004
    assert "2004" in (report.image.note or "")
    # Lens matches become citable evidence items.
    assert any(e.channel == "lens" for e in report.evidence)
    # 3 text searches + 1 lens search; the photo claim costs no extra searches.
    assert report.searches_used == 4
    # A forward with a photo always carries the "this photo shows the event"
    # claim; a 2004 photo makes the whole forward OUTDATED even though the
    # text claim itself stays unverified in rule-based mode.
    photo_claims = [c for c in report.claims if c.kind == "image_context"]
    assert len(photo_claims) == 1
    photo_verdict = next(v for v in report.verdicts if v.claim_id == photo_claims[0].id)
    assert photo_verdict.label == VerdictLabel.OUTDATED
    assert "2004" in photo_verdict.rationale
    assert report.overall_label == VerdictLabel.OUTDATED


def test_no_input_raises():
    import pytest

    with pytest.raises(ValueError):
        check("")


def test_missing_key_message_is_helpful(monkeypatch):
    monkeypatch.delenv("KASAUTI_OFFLINE", raising=False)
    from kasauti.serp import KasautiError

    import pytest

    with pytest.raises(KasautiError, match="SERPAPI_API_KEY"):
        SerpSearcher(offline=False)


def test_report_is_json_serialisable():
    report = check(UNESCO)
    payload = report.model_dump_json()
    assert "overall_label" in payload
