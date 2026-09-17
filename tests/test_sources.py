from kasauti.models import SourceTier
from kasauti.sources import classify_domain, classify_url, domain_of, factcheck_sweep_query


def test_fact_checker_tier():
    cred = classify_domain("altnews.in")
    assert cred.tier == SourceTier.FACT_CHECKER
    assert cred.weight == 1.0
    assert "Alt News" in cred.label


def test_subdomain_matches_parent():
    assert classify_domain("www.boomlive.in").tier == SourceTier.FACT_CHECKER
    assert classify_domain("hindi.boomlive.in").tier == SourceTier.FACT_CHECKER


def test_gov_in_suffix_is_official():
    assert classify_domain("tax.karnataka.gov.in").tier == SourceTier.OFFICIAL
    assert classify_domain("pib.gov.in").tier == SourceTier.OFFICIAL


def test_national_outlet():
    assert classify_domain("thehindu.com").tier == SourceTier.NATIONAL


def test_reference_tier_for_provenance_sources():
    cred = classify_domain("en.wikipedia.org")
    assert cred.tier == SourceTier.REFERENCE
    assert 0.55 < cred.weight < 0.75  # stronger than unknown, weaker than a newsroom


def test_satire_flagged():
    assert classify_domain("fakingnews.com").tier == SourceTier.SATIRE


def test_unknown_gets_low_weight_not_zero():
    cred = classify_domain("random-viral-blog.xyz")
    assert cred.tier == SourceTier.UNKNOWN
    assert 0 < cred.weight < 0.5


def test_domain_of_url():
    assert domain_of("https://www.altnews.in/some/story?utm=x") == "altnews.in"
    assert domain_of("boomlive.in/path") == "boomlive.in"


def test_classify_url():
    assert classify_url("https://reuters.com/article/x").tier == SourceTier.WIRE


def test_sweep_query_contains_sites():
    q = factcheck_sweep_query("unesco anthem")
    assert q.startswith("unesco anthem (site:")
    assert "site:altnews.in" in q
    assert " OR " in q
