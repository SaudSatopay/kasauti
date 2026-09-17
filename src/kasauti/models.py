"""Pydantic models shared across the Kasauti pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class VerdictLabel(str, Enum):
    TRUE = "true"
    MOSTLY_TRUE = "mostly_true"
    MISLEADING = "misleading"
    FALSE = "false"
    OUTDATED = "outdated"          # real once, recycled as current news
    UNVERIFIED = "unverified"
    SATIRE = "satire"

    @property
    def display(self) -> str:
        return {
            VerdictLabel.TRUE: "True",
            VerdictLabel.MOSTLY_TRUE: "Mostly true",
            VerdictLabel.MISLEADING: "Misleading",
            VerdictLabel.FALSE: "False",
            VerdictLabel.OUTDATED: "Outdated / recycled",
            VerdictLabel.UNVERIFIED: "Unverified",
            VerdictLabel.SATIRE: "Satire",
        }[self]

    @property
    def severity(self) -> int:
        """Higher = worse. Used to pick the headline verdict for a forward."""
        return {
            VerdictLabel.FALSE: 6,
            VerdictLabel.SATIRE: 5,
            VerdictLabel.MISLEADING: 4,
            VerdictLabel.OUTDATED: 3,
            VerdictLabel.UNVERIFIED: 2,
            VerdictLabel.MOSTLY_TRUE: 1,
            VerdictLabel.TRUE: 0,
        }[self]


class SourceTier(str, Enum):
    FACT_CHECKER = "fact_checker"    # IFCN-style dedicated fact-checking desks
    OFFICIAL = "official"            # government / regulator / intl. bodies
    WIRE = "wire"                    # news agencies
    INTERNATIONAL = "international"  # major global outlets
    NATIONAL = "national"            # major Indian outlets
    REGIONAL = "regional"            # smaller/regional outlets
    SATIRE = "satire"                # known satire publications
    UNKNOWN = "unknown"


class Credibility(BaseModel):
    tier: SourceTier = SourceTier.UNKNOWN
    label: str = "Unrecognised source"
    weight: float = 0.35


class FingerprintSignal(BaseModel):
    id: str
    label: str
    detail: str
    weight: int


class Fingerprint(BaseModel):
    """Deterministic 'does this even smell like a chain forward?' score (0–100)."""
    score: int = 0
    level: str = "low"  # low | medium | high
    signals: list[FingerprintSignal] = Field(default_factory=list)


class Claim(BaseModel):
    id: str                       # C1, C2, ...
    text_en: str                  # normalised English form used for search
    original_excerpt: Optional[str] = None
    kind: str = "other"           # event|statistic|health|scheme|job|quote|image_context|other
    queries: list[str] = Field(default_factory=list)


class ClaimExtraction(BaseModel):
    language: str = "en"          # BCP-47-ish code reported by the LLM
    language_name: str = "English"
    translation_en: Optional[str] = None
    summary: Optional[str] = None
    claims: list[Claim] = Field(default_factory=list)
    llm_used: bool = False


class EvidenceItem(BaseModel):
    id: str                       # E1, E2, ...
    claim_id: Optional[str] = None
    channel: str = "web"          # web | news | factcheck | lens
    title: str
    link: str
    domain: str
    source_name: Optional[str] = None
    snippet: Optional[str] = None
    date_raw: Optional[str] = None
    date: Optional[datetime] = None
    credibility: Credibility = Field(default_factory=Credibility)
    score: float = 0.0
    favicon: Optional[str] = None


class ImageMatch(BaseModel):
    title: Optional[str] = None
    link: Optional[str] = None
    domain: Optional[str] = None
    source: Optional[str] = None
    date_raw: Optional[str] = None
    date: Optional[datetime] = None
    thumbnail: Optional[str] = None


class ImageAnalysis(BaseModel):
    image_url: str
    matches: list[ImageMatch] = Field(default_factory=list)
    distinct_domains: int = 0
    earliest_date: Optional[datetime] = None
    earliest_domain: Optional[str] = None
    note: Optional[str] = None


class ClaimVerdict(BaseModel):
    claim_id: str
    label: VerdictLabel = VerdictLabel.UNVERIFIED
    confidence: float = 0.3
    rationale: str = ""
    citation_ids: list[str] = Field(default_factory=list)
    guardrail_notes: list[str] = Field(default_factory=list)


class Report(BaseModel):
    """Everything Kasauti learned about one forward."""
    input_text: str
    image_url: Optional[str] = None
    language: str = "en"
    language_name: str = "English"
    translation_en: Optional[str] = None
    fingerprint: Fingerprint = Field(default_factory=Fingerprint)
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    image: Optional[ImageAnalysis] = None
    verdicts: list[ClaimVerdict] = Field(default_factory=list)
    overall_label: VerdictLabel = VerdictLabel.UNVERIFIED
    overall_confidence: float = 0.3
    overall_summary: str = ""
    suggested_reply: Optional[str] = None
    suggested_reply_lang: Optional[str] = None
    searches_used: int = 0
    llm_used: bool = False
    offline: bool = False
    elapsed_s: float = 0.0
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    def evidence_by_id(self, eid: str) -> Optional[EvidenceItem]:
        for item in self.evidence:
            if item.id == eid:
                return item
        return None
