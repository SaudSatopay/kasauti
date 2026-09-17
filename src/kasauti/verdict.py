"""Verdict synthesis — evidence in, calibrated verdicts out.

Two paths:
  * LLM-as-judge over a numbered, credibility-tagged evidence table, followed
    by deterministic guardrails (an LLM may not claim more certainty than the
    evidence supports).
  * A conservative rule-based path when no LLM is configured: fact-checker
    debunk headlines can push a claim to "false"; everything else stays
    "unverified" with the evidence laid out for the reader.
"""
from __future__ import annotations

import re
from typing import Optional

from .llm import LLM
from .models import (
    Claim,
    ClaimVerdict,
    EvidenceItem,
    ImageAnalysis,
    SourceTier,
    VerdictLabel,
)

_JUDGE_SYSTEM = """You are the verdict module of Kasauti, an evidence-first misinformation
checker for India. You will receive one claim and a numbered table of evidence collected from
live web search. Each evidence row is tagged with its source category (Fact-checker, Official,
News agency, National outlet, etc.) and date.

Weigh evidence by source category: dedicated fact-checkers and official sources outrank
ordinary outlets; unrecognised sites count for very little. Pay attention to dates — a claim
that was true years ago but is presented as current news is "outdated". If a fact-checker has
directly addressed this claim, their finding should normally decide the verdict.

Return ONLY a JSON object:
{
  "label": "true|mostly_true|misleading|false|outdated|unverified|satire",
  "confidence": <0.0-1.0, how strongly the evidence supports the label>,
  "rationale": "<2-3 plain sentences, max 70 words, citing evidence ids like [E2]>",
  "citations": ["E2", "E5"]
}

Calibration rules:
- Cite only evidence ids that actually appear in the table.
- If the evidence does not clearly address the claim, the label is "unverified" and the
  confidence is low. Never guess from your own memory; judge ONLY from the table.
- "false" or "true" with confidence above 0.8 requires at least one Fact-checker or Official
  source directly on point."""

_DEBUNK_WORDS = re.compile(
    r"\b(fake|false|hoax|fact[- ]?check|misleading|debunk\w*|no,|myth|scam|"
    r"fabricat\w*|morphed|edited|doctored|old (video|photo|image)|"
    r"फर्जी|झूठ|गलत|अफवाह|पड़ताल)\b",
    re.IGNORECASE,
)
_CONFIRM_WORDS = re.compile(r"\b(confirm\w*|official\w*|announce\w*|yes,|correct|सही|पुष्टि)\b", re.I)

_VALID_LABELS = {label.value for label in VerdictLabel}


def _evidence_table(evidence: list[EvidenceItem]) -> str:
    lines = []
    for e in evidence:
        date = e.date.date().isoformat() if e.date else (e.date_raw or "no date")
        snippet = (e.snippet or "").strip().replace("\n", " ")[:220]
        lines.append(
            f"[{e.id}] ({e.credibility.label} · {date} · via {e.channel}) "
            f"{e.title.strip()[:160]} — {snippet} <{e.domain}>"
        )
    return "\n".join(lines) if lines else "(no evidence found)"


def _apply_guardrails(
    verdict: ClaimVerdict, evidence: list[EvidenceItem], image: Optional[ImageAnalysis]
) -> ClaimVerdict:
    by_id = {e.id: e for e in evidence}
    verdict.citation_ids = [c for c in verdict.citation_ids if c in by_id]
    cited = [by_id[c] for c in verdict.citation_ids]
    cited_tiers = {e.credibility.tier for e in cited}

    strong_tiers = {
        SourceTier.FACT_CHECKER, SourceTier.OFFICIAL, SourceTier.WIRE,
        SourceTier.INTERNATIONAL, SourceTier.NATIONAL,
    }

    if not cited:
        if verdict.label != VerdictLabel.UNVERIFIED:
            verdict.guardrail_notes.append(
                f"Downgraded from '{verdict.label.value}' — the verdict cited no evidence."
            )
            verdict.label = VerdictLabel.UNVERIFIED
        verdict.confidence = min(verdict.confidence, 0.35)
    elif not (cited_tiers & strong_tiers):
        if verdict.confidence > 0.55:
            verdict.guardrail_notes.append(
                "Confidence capped at 0.55 — no recognised newsroom, fact-checker or "
                "official source among the citations."
            )
        verdict.confidence = min(verdict.confidence, 0.55)

    if verdict.label in (VerdictLabel.TRUE, VerdictLabel.FALSE) and verdict.confidence > 0.8:
        decisive = {SourceTier.FACT_CHECKER, SourceTier.OFFICIAL}
        if not (cited_tiers & decisive):
            verdict.guardrail_notes.append(
                "Confidence capped at 0.8 — a definitive true/false above 0.8 needs a "
                "fact-checker or official source."
            )
            verdict.confidence = 0.8

    if any(e.credibility.tier == SourceTier.SATIRE for e in cited):
        if verdict.label != VerdictLabel.SATIRE:
            verdict.guardrail_notes.append(
                "Relabelled as satire — cited evidence traces to a satire publication."
            )
            verdict.label = VerdictLabel.SATIRE

    verdict.confidence = max(0.05, min(0.99, round(verdict.confidence, 2)))
    return verdict


def _rule_based(claim: Claim, evidence: list[EvidenceItem]) -> ClaimVerdict:
    """No-LLM path: deliberately conservative."""
    from .evidence import relevance

    # A debunk headline only counts if it plausibly concerns THIS claim —
    # a fact-checker debunking something unrelated is not evidence here.
    fc_debunks = [
        e for e in evidence
        if e.credibility.tier == SourceTier.FACT_CHECKER
        and _DEBUNK_WORDS.search(f"{e.title} {e.snippet or ''}")
        and relevance(claim.text_en, e.title, e.snippet) >= 0.15
    ]
    if fc_debunks:
        top = sorted(fc_debunks, key=lambda e: e.score, reverse=True)[:3]
        names = ", ".join(sorted({e.source_name or e.domain for e in top}))
        return ClaimVerdict(
            claim_id=claim.id,
            label=VerdictLabel.FALSE,
            confidence=0.6 if len(fc_debunks) == 1 else 0.7,
            rationale=(
                f"Fact-checking desks ({names}) have published pieces matching this claim "
                f"with debunk language in the headline "
                f"({', '.join('[' + e.id + ']' for e in top)}). Rule-based mode: read the "
                f"linked checks to confirm the details."
            ),
            citation_ids=[e.id for e in top],
        )

    official_hits = [
        e for e in evidence
        if e.credibility.tier == SourceTier.OFFICIAL
        and _CONFIRM_WORDS.search(f"{e.title} {e.snippet or ''}")
    ]
    if official_hits:
        top = official_hits[0]
        return ClaimVerdict(
            claim_id=claim.id,
            label=VerdictLabel.UNVERIFIED,
            confidence=0.45,
            rationale=(
                f"An official source may address this claim directly [{top.id}]. "
                f"Rule-based mode cannot read past the headline — open the link to verify."
            ),
            citation_ids=[top.id],
        )

    count = len(evidence)
    return ClaimVerdict(
        claim_id=claim.id,
        label=VerdictLabel.UNVERIFIED,
        confidence=0.3 if count else 0.2,
        rationale=(
            f"No fact-check verdict found in headlines across {count} results. "
            "Review the evidence list — and treat the claim as unconfirmed until a "
            "reliable source reports it."
            if count else
            "Search returned no usable evidence for this claim — a strong hint that no "
            "reputable outlet is reporting it."
        ),
        citation_ids=[e.id for e in evidence[:3]],
    )


def judge_claim(
    claim: Claim,
    evidence: list[EvidenceItem],
    *,
    llm: Optional[LLM] = None,
    image: Optional[ImageAnalysis] = None,
) -> ClaimVerdict:
    llm = llm or LLM()
    if not llm.available:
        return _apply_guardrails(_rule_based(claim, evidence), evidence, image)

    user = f'CLAIM {claim.id}: "{claim.text_en}"\n(kind: {claim.kind})\n\nEVIDENCE TABLE:\n'
    user += _evidence_table(evidence)
    if image is not None:
        user += f"\n\nIMAGE ANALYSIS (Google Lens): {image.note}"
        if image.earliest_date:
            user += f"\nEarliest dated appearance: {image.earliest_date.date().isoformat()}"

    data = llm.chat_json(_JUDGE_SYSTEM, user)
    if not data:
        return _apply_guardrails(_rule_based(claim, evidence), evidence, image)

    label_raw = str(data.get("label") or "unverified").strip().lower()
    label = VerdictLabel(label_raw) if label_raw in _VALID_LABELS else VerdictLabel.UNVERIFIED
    try:
        confidence = float(data.get("confidence", 0.3))
    except (TypeError, ValueError):
        confidence = 0.3
    citations = [str(c).strip().upper() for c in (data.get("citations") or [])]

    verdict = ClaimVerdict(
        claim_id=claim.id,
        label=label,
        confidence=confidence,
        rationale=str(data.get("rationale") or "").strip()[:600],
        citation_ids=citations,
    )
    return _apply_guardrails(verdict, evidence, image)


def overall_verdict(verdicts: list[ClaimVerdict]) -> tuple[VerdictLabel, float]:
    """Headline verdict for the whole forward: the worst well-supported label."""
    if not verdicts:
        return VerdictLabel.UNVERIFIED, 0.3
    confident = [v for v in verdicts if v.confidence >= 0.45]
    pool = confident or verdicts
    worst = max(pool, key=lambda v: (v.label.severity, v.confidence))
    avg_conf = sum(v.confidence for v in pool) / len(pool)
    return worst.label, round(min(avg_conf, worst.confidence + 0.1), 2)
