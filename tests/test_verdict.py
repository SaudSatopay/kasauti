from kasauti.models import Claim, ClaimVerdict, Credibility, EvidenceItem, SourceTier, VerdictLabel
from kasauti.verdict import _apply_guardrails, _rule_based, overall_verdict


def _ev(eid: str, tier: SourceTier, title: str = "title", snippet: str = "") -> EvidenceItem:
    weights = {SourceTier.FACT_CHECKER: 1.0, SourceTier.UNKNOWN: 0.35,
               SourceTier.SATIRE: 0.2, SourceTier.OFFICIAL: 0.95}
    return EvidenceItem(
        id=eid, title=title, link=f"https://example.com/{eid}", domain="example.com",
        snippet=snippet,
        credibility=Credibility(tier=tier, label=str(tier.value), weight=weights.get(tier, 0.5)),
        score=1.0,
    )


def _claim() -> Claim:
    return Claim(id="C1", text_en="UNESCO declared the Indian anthem the best", queries=["q"])


def test_guardrail_no_citations_downgrades_to_unverified():
    v = ClaimVerdict(claim_id="C1", label=VerdictLabel.FALSE, confidence=0.95,
                     rationale="sure of it", citation_ids=[])
    out = _apply_guardrails(v, [], None)
    assert out.label == VerdictLabel.UNVERIFIED
    assert out.confidence <= 0.35
    assert out.guardrail_notes


def test_guardrail_unknown_sources_cap_confidence():
    ev = [_ev("E1", SourceTier.UNKNOWN)]
    v = ClaimVerdict(claim_id="C1", label=VerdictLabel.FALSE, confidence=0.9,
                     rationale="", citation_ids=["E1"])
    out = _apply_guardrails(v, ev, None)
    assert out.confidence <= 0.55


def test_guardrail_high_confidence_needs_decisive_tier():
    ev = [_ev("E1", SourceTier.FACT_CHECKER)]
    v = ClaimVerdict(claim_id="C1", label=VerdictLabel.FALSE, confidence=0.95,
                     rationale="", citation_ids=["E1"])
    out = _apply_guardrails(v, ev, None)
    assert out.confidence == 0.95  # fact-checker cited → high confidence allowed


def test_guardrail_satire_relabels():
    ev = [_ev("E1", SourceTier.SATIRE)]
    v = ClaimVerdict(claim_id="C1", label=VerdictLabel.FALSE, confidence=0.7,
                     rationale="", citation_ids=["E1"])
    out = _apply_guardrails(v, ev, None)
    assert out.label == VerdictLabel.SATIRE


def test_guardrail_drops_invalid_citation_ids():
    v = ClaimVerdict(claim_id="C1", label=VerdictLabel.TRUE, confidence=0.9,
                     rationale="", citation_ids=["E99"])
    out = _apply_guardrails(v, [], None)
    assert out.citation_ids == []
    assert out.label == VerdictLabel.UNVERIFIED


def test_rule_based_factchecker_debunk_yields_false():
    ev = [
        _ev("E1", SourceTier.FACT_CHECKER,
            title="No, UNESCO has not declared the anthem best — fact check",
            snippet="the viral claim is false"),
        _ev("E2", SourceTier.FACT_CHECKER,
            title="UNESCO anthem hoax debunked again"),
    ]
    out = _rule_based(_claim(), ev)
    assert out.label == VerdictLabel.FALSE
    assert out.confidence >= 0.6
    assert out.citation_ids


def test_rule_based_no_evidence_is_unverified():
    out = _rule_based(_claim(), [])
    assert out.label == VerdictLabel.UNVERIFIED
    assert out.confidence <= 0.3


def test_rule_based_ignores_unrelated_debunks():
    # A fact-checker debunking something else entirely must not flip THIS claim.
    ev = [
        _ev("E1", SourceTier.FACT_CHECKER,
            title="Fact check: old video of Mexico airport shared as Mumbai rains",
            snippet="the viral video is false"),
        _ev("E2", SourceTier.FACT_CHECKER,
            title="No, this hoax about free laptops is fake"),
    ]
    out = _rule_based(_claim(), ev)
    assert out.label == VerdictLabel.UNVERIFIED


def test_overall_verdict_worst_wins():
    verdicts = [
        ClaimVerdict(claim_id="C1", label=VerdictLabel.TRUE, confidence=0.9),
        ClaimVerdict(claim_id="C2", label=VerdictLabel.FALSE, confidence=0.7),
    ]
    label, conf = overall_verdict(verdicts)
    assert label == VerdictLabel.FALSE
    assert 0 < conf <= 1


def test_overall_verdict_ignores_low_confidence_noise():
    verdicts = [
        ClaimVerdict(claim_id="C1", label=VerdictLabel.FALSE, confidence=0.2),
        ClaimVerdict(claim_id="C2", label=VerdictLabel.TRUE, confidence=0.9),
    ]
    label, _ = overall_verdict(verdicts)
    assert label == VerdictLabel.TRUE


def test_overall_verdict_empty():
    label, conf = overall_verdict([])
    assert label == VerdictLabel.UNVERIFIED
