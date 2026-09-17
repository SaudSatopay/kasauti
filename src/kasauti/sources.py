"""Source credibility registry.

Kasauti does not treat all search results equally. Evidence is weighted by the
publisher's *category* — dedicated fact-checking desks and official government
domains carry the most weight, unrecognised blogs the least. The registry is a
transparent, editable list (PRs welcome); it encodes publisher *type*, not any
judgement of editorial stance.

Tiers (see models.SourceTier):
  fact_checker  — dedicated fact-checking organisations (IFCN signatories and
                  similar), which publish claim-level verdicts.
  official      — government / regulator / international institutions.
  wire          — news agencies.
  international — major global newsrooms.
  national      — major Indian newsrooms.
  regional      — recognised regional outlets.
  satire        — self-declared satire publications (a "match" here usually
                  means the forward IS the joke).
"""
from __future__ import annotations

from urllib.parse import urlparse

from .models import Credibility, SourceTier

TIER_WEIGHTS: dict[SourceTier, float] = {
    SourceTier.FACT_CHECKER: 1.00,
    SourceTier.OFFICIAL: 0.95,
    SourceTier.WIRE: 0.85,
    SourceTier.INTERNATIONAL: 0.80,
    SourceTier.NATIONAL: 0.75,
    SourceTier.REGIONAL: 0.55,
    SourceTier.REFERENCE: 0.60,
    SourceTier.SATIRE: 0.20,
    SourceTier.UNKNOWN: 0.35,
}

TIER_LABELS: dict[SourceTier, str] = {
    SourceTier.FACT_CHECKER: "Fact-checker",
    SourceTier.OFFICIAL: "Official / Government",
    SourceTier.WIRE: "News agency",
    SourceTier.INTERNATIONAL: "International outlet",
    SourceTier.NATIONAL: "National outlet",
    SourceTier.REGIONAL: "Regional outlet",
    SourceTier.REFERENCE: "Reference",
    SourceTier.SATIRE: "Satire",
    SourceTier.UNKNOWN: "Unrecognised source",
}

# Encyclopaedic / archival sources: strong for provenance ("this photo is the
# 2004 tsunami"), weaker than a newsroom for breaking claims.
REFERENCE: dict[str, str] = {
    "wikipedia.org": "Wikipedia",
    "wikimedia.org": "Wikimedia Commons",
    "britannica.com": "Britannica",
    "archive.org": "Internet Archive",
}

# Dedicated fact-checking desks active on Indian misinformation.
FACT_CHECKERS: dict[str, str] = {
    "altnews.in": "Alt News",
    "boomlive.in": "BOOM",
    "factly.in": "Factly",
    "vishvasnews.com": "Vishvas News",
    "newschecker.in": "Newschecker",
    "factcrescendo.com": "Fact Crescendo",
    "thip.media": "THIP Media (health)",
    "newsmeter.in": "NewsMeter",
    "youturn.in": "YouTurn (Tamil)",
    "dfrac.org": "DFRAC",
    "logicallyfacts.com": "Logically Facts",
    "factchecker.in": "FactChecker.in",
    # Global desks that frequently cover Indian claims:
    "factcheck.afp.com": "AFP Fact Check",
    "snopes.com": "Snopes",
    "fullfact.org": "Full Fact",
    "politifact.com": "PolitiFact",
    "leadstories.com": "Lead Stories",
}

# Subset used to build the `site:` sweep query (keep the query short).
FACT_CHECK_SWEEP_DOMAINS: list[str] = [
    "altnews.in",
    "boomlive.in",
    "factly.in",
    "vishvasnews.com",
    "newschecker.in",
    "factcrescendo.com",
    "factcheck.afp.com",
    "pib.gov.in",
]

OFFICIAL: dict[str, str] = {
    "pib.gov.in": "PIB (Press Information Bureau)",
    "mygov.in": "MyGov",
    "rbi.org.in": "Reserve Bank of India",
    "eci.gov.in": "Election Commission of India",
    "uidai.gov.in": "UIDAI",
    "mohfw.gov.in": "Ministry of Health & Family Welfare",
    "isro.gov.in": "ISRO",
    "who.int": "World Health Organization",
    "un.org": "United Nations",
    "unesco.org": "UNESCO",
    "imd.gov.in": "India Meteorological Department",
    "ncdc.mohfw.gov.in": "NCDC",
    "cybercrime.gov.in": "National Cyber Crime Portal",
}

# Any *.gov.in / *.nic.in / *.gov domain is treated as official even if not
# listed above.
OFFICIAL_SUFFIXES: tuple[str, ...] = (".gov.in", ".nic.in", ".gov")

WIRES: dict[str, str] = {
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press",
    "ptinews.com": "PTI",
    "aninews.in": "ANI",
    "ians.in": "IANS",
    "afp.com": "AFP",
}

INTERNATIONAL: dict[str, str] = {
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "theguardian.com": "The Guardian",
    "nytimes.com": "The New York Times",
    "washingtonpost.com": "The Washington Post",
    "aljazeera.com": "Al Jazeera",
    "dw.com": "DW",
    "cnn.com": "CNN",
    "economist.com": "The Economist",
    "ft.com": "Financial Times",
    "bloomberg.com": "Bloomberg",
}

NATIONAL: dict[str, str] = {
    "thehindu.com": "The Hindu",
    "indianexpress.com": "The Indian Express",
    "hindustantimes.com": "Hindustan Times",
    "timesofindia.indiatimes.com": "The Times of India",
    "indiatimes.com": "Times Group",
    "ndtv.com": "NDTV",
    "news18.com": "News18",
    "indiatoday.in": "India Today",
    "deccanherald.com": "Deccan Herald",
    "telegraphindia.com": "The Telegraph (India)",
    "livemint.com": "Mint",
    "economictimes.indiatimes.com": "The Economic Times",
    "business-standard.com": "Business Standard",
    "scroll.in": "Scroll.in",
    "theprint.in": "ThePrint",
    "thewire.in": "The Wire",
    "tribuneindia.com": "The Tribune",
    "thequint.com": "The Quint",
    "firstpost.com": "Firstpost",
    "dnaindia.com": "DNA India",
    "jagran.com": "Dainik Jagran",
    "bhaskar.com": "Dainik Bhaskar",
    "amarujala.com": "Amar Ujala",
    "aajtak.in": "Aaj Tak",
    "abplive.com": "ABP News",
    "zeenews.india.com": "Zee News",
    "navbharattimes.indiatimes.com": "Navbharat Times",
    "manoramaonline.com": "Malayala Manorama",
    "mathrubhumi.com": "Mathrubhumi",
    "anandabazar.com": "Anandabazar Patrika",
    "eenadu.net": "Eenadu",
    "dinamalar.com": "Dinamalar",
    "lokmat.com": "Lokmat",
}

SATIRE: dict[str, str] = {
    "fakingnews.com": "Faking News (satire)",
    "theunrealtimes.com": "The UnReal Times (satire)",
    "theonion.com": "The Onion (satire)",
    "babylonbee.com": "The Babylon Bee (satire)",
    "thedeshbhakt.in": "The Deshbhakt (satire/commentary)",
}

_REGISTRY: list[tuple[dict[str, str], SourceTier]] = [
    (FACT_CHECKERS, SourceTier.FACT_CHECKER),
    (OFFICIAL, SourceTier.OFFICIAL),
    (WIRES, SourceTier.WIRE),
    (INTERNATIONAL, SourceTier.INTERNATIONAL),
    (NATIONAL, SourceTier.NATIONAL),
    (REFERENCE, SourceTier.REFERENCE),
    (SATIRE, SourceTier.SATIRE),
]


def domain_of(url: str) -> str:
    """Return a normalised registrable-ish domain for a URL."""
    try:
        netloc = urlparse(url if "://" in url else f"https://{url}").netloc
    except ValueError:
        return ""
    host = netloc.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def classify_domain(domain: str) -> Credibility:
    """Map a domain to a credibility tier. Unknown domains get a low weight,
    not zero — an unrecognised source is weak evidence, not anti-evidence."""
    domain = (domain or "").lower().lstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain:
        return Credibility()

    for table, tier in _REGISTRY:
        for known, name in table.items():
            if domain == known or domain.endswith("." + known):
                return Credibility(
                    tier=tier,
                    label=f"{TIER_LABELS[tier]} · {name}",
                    weight=TIER_WEIGHTS[tier],
                )

    for suffix in OFFICIAL_SUFFIXES:
        if domain.endswith(suffix):
            return Credibility(
                tier=SourceTier.OFFICIAL,
                label=f"{TIER_LABELS[SourceTier.OFFICIAL]} · {domain}",
                weight=TIER_WEIGHTS[SourceTier.OFFICIAL],
            )

    # Recognisable news-ish TLD heuristics could go here; default to unknown.
    return Credibility(
        tier=SourceTier.UNKNOWN,
        label=f"{TIER_LABELS[SourceTier.UNKNOWN]} · {domain}",
        weight=TIER_WEIGHTS[SourceTier.UNKNOWN],
    )


def classify_url(url: str) -> Credibility:
    return classify_domain(domain_of(url))


def factcheck_sweep_query(query: str) -> str:
    """Build one Google query that sweeps the major Indian fact-check desks."""
    sites = " OR ".join(f"site:{d}" for d in FACT_CHECK_SWEEP_DOMAINS)
    return f"{query} ({sites})"
