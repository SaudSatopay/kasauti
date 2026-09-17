"""Kasauti (कसौटी) — the touchstone for WhatsApp forwards.

An evidence-first misinformation checker for India, powered by SerpApi.

    from kasauti import check
    report = check("UNESCO ne Indian national anthem ko best declare kiya!")
    print(report.overall_label, report.overall_confidence)
"""
from .fingerprint import fingerprint
from .models import (
    Claim,
    ClaimVerdict,
    EvidenceItem,
    Fingerprint,
    ImageAnalysis,
    Report,
    SourceTier,
    VerdictLabel,
)
from .pipeline import check
from .serp import KasautiError, SerpSearcher

__version__ = "0.1.0"

__all__ = [
    "check",
    "fingerprint",
    "Report",
    "Claim",
    "ClaimVerdict",
    "EvidenceItem",
    "Fingerprint",
    "ImageAnalysis",
    "SourceTier",
    "VerdictLabel",
    "SerpSearcher",
    "KasautiError",
    "__version__",
]
