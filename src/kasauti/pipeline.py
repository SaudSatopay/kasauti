"""The Kasauti pipeline — one function that takes a forward and returns a Report.

Stages (progress events are emitted for each, so UIs can narrate the work):

  1. fingerprint   — offline chain-forward heuristics
  2. claims        — extract atomic claims (LLM, with rule-based fallback)
  3. search        — SerpApi retrieval, all claims × 3 strategies in parallel,
                     plus Google Lens when an image is attached
  4. evidence      — normalise, dedupe, credibility-rank
  5. verdicts      — per-claim judgement with calibration guardrails
  6. reply         — draft the paste-into-the-group correction
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from .claims import extract_claims
from .evidence import build_evidence, normalize_news, normalize_web
from .fingerprint import fingerprint
from .imagecheck import analyze_lens, lens_evidence
from .llm import LLM
from .models import Claim, EvidenceItem, ImageAnalysis, Report, VerdictLabel
from .reply import suggest_reply
from .serp import SerpSearcher
from .verdict import judge_claim, overall_verdict

ProgressFn = Callable[[str, str], None]


def _emit(on_event: Optional[ProgressFn], stage: str, detail: str) -> None:
    if on_event:
        try:
            on_event(stage, detail)
        except Exception:
            pass  # a broken progress listener must never kill a check


def _search_claim(searcher: SerpSearcher, claim: Claim) -> list[list[dict[str, Any]]]:
    """Run the three text-retrieval strategies for one claim."""
    primary = claim.queries[0] if claim.queries else claim.text_en[:100]
    secondary = claim.queries[1] if len(claim.queries) > 1 else None

    batches: list[list[dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_web = pool.submit(searcher.web, primary)
        fut_news = pool.submit(searcher.news, secondary or primary)
        fut_fc = pool.submit(searcher.factcheck_sweep, primary)
        for fut, normalizer, channel in (
            (fut_web, normalize_web, "web"),
            (fut_news, normalize_news, None),
            (fut_fc, normalize_web, "factcheck"),
        ):
            try:
                raw = fut.result()
            except Exception:
                raw = {}
            if normalizer is normalize_news:
                batches.append(normalize_news(raw))
            else:
                batches.append(normalize_web(raw, channel=channel or "web"))
    return batches


def check(
    text: str = "",
    image_url: Optional[str] = None,
    *,
    searcher: Optional[SerpSearcher] = None,
    llm: Optional[LLM] = None,
    reply_language: Optional[str] = None,
    on_event: Optional[ProgressFn] = None,
) -> Report:
    """Verify one forward. `text` and/or `image_url` must be provided."""
    text = (text or "").strip()
    if not text and not image_url:
        raise ValueError("Provide the forward text, an image URL, or both.")

    started = time.time()
    searcher = searcher or SerpSearcher()
    llm = llm or LLM()

    # 1 — fingerprint (free, instant)
    _emit(on_event, "fingerprint", "Reading the message for chain-forward markers…")
    fp = fingerprint(text)
    if fp.signals:
        top = ", ".join(s.label for s in fp.signals[:3])
        _emit(on_event, "fingerprint", f"Fingerprint {fp.score}/100 ({fp.level}): {top}")

    # 2 — claims
    _emit(on_event, "claims",
          "Extracting checkable claims…" if llm.available
          else "No LLM configured — using rule-based claim handling.")
    extraction = extract_claims(text, image_url=image_url, llm=llm)
    searchable = [c for c in extraction.claims if c.queries]
    for c in searchable:
        _emit(on_event, "claims", f"{c.id}: {c.text_en}")

    # 3 — search (claims in parallel; Lens alongside)
    n_calls = len(searchable) * 3 + (1 if image_url else 0)
    _emit(on_event, "search",
          f"Searching live via SerpApi — {n_calls} searches across Google, "
          f"Google News, fact-check desks{' and Google Lens' if image_url else ''}…")

    image_analysis: Optional[ImageAnalysis] = None
    raw_by_claim: dict[str, list[list[dict[str, Any]]]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        claim_futs = {c.id: pool.submit(_search_claim, searcher, c) for c in searchable}
        lens_fut = pool.submit(searcher.lens, image_url) if image_url else None
        for cid, fut in claim_futs.items():
            try:
                raw_by_claim[cid] = fut.result()
            except Exception:
                raw_by_claim[cid] = []
        if lens_fut is not None:
            try:
                image_analysis = analyze_lens(image_url, lens_fut.result())  # type: ignore[arg-type]
            except Exception:
                image_analysis = ImageAnalysis(
                    image_url=image_url or "",
                    note="Google Lens lookup failed — image left unanalysed.",
                )

    # 4 — evidence
    _emit(on_event, "evidence", "Weighing sources by credibility and recency…")
    all_evidence: list[EvidenceItem] = []
    evidence_by_claim: dict[str, list[EvidenceItem]] = {}
    next_index = 1
    for claim in searchable:
        items = build_evidence(claim, raw_by_claim.get(claim.id, []),
                               start_index=next_index)
        next_index += len(items)
        evidence_by_claim[claim.id] = items
        all_evidence.extend(items)
    if image_analysis is not None:
        lens_items = lens_evidence(image_analysis, start_index=next_index)
        next_index += len(lens_items)
        all_evidence.extend(lens_items)
        for claim in searchable:
            if claim.kind == "image_context":
                evidence_by_claim[claim.id] = evidence_by_claim.get(claim.id, []) + lens_items
    _emit(on_event, "evidence",
          f"{len(all_evidence)} distinct sources kept after deduplication.")

    # 5 — verdicts
    _emit(on_event, "verdicts", "Judging each claim against the evidence…")
    verdicts = []
    for claim in searchable:
        v = judge_claim(claim, evidence_by_claim.get(claim.id, []),
                        llm=llm, image=image_analysis)
        verdicts.append(v)
        _emit(on_event, "verdicts",
              f"{claim.id}: {v.label.display} ({v.confidence:.0%})")

    label, confidence = overall_verdict(verdicts)

    report = Report(
        input_text=text,
        image_url=image_url,
        language=extraction.language,
        language_name=extraction.language_name,
        translation_en=extraction.translation_en,
        fingerprint=fp,
        claims=extraction.claims,
        evidence=all_evidence,
        image=image_analysis,
        verdicts=verdicts,
        overall_label=label,
        overall_confidence=confidence,
        overall_summary=extraction.summary or "",
        searches_used=searcher.searches_used,
        llm_used=extraction.llm_used or llm.available,
        offline=searcher.offline,
    )

    # 6 — reply
    _emit(on_event, "reply", "Drafting a polite reply for the group…")
    reply_text, reply_lang = suggest_reply(report, llm=llm, reply_language=reply_language)
    report.suggested_reply = reply_text
    report.suggested_reply_lang = reply_lang

    if not report.overall_summary:
        report.overall_summary = (
            f"Verdict: {label.display}. "
            + (f"{len(verdicts)} claim(s) checked against {len(all_evidence)} sources."
               if verdicts else "No independently checkable claim was found in this message.")
        )
    if not verdicts and fp.score >= 55:
        report.overall_label = VerdictLabel.UNVERIFIED
        report.overall_summary += (
            " The message still carries strong chain-forward markers — treat with caution."
        )

    report.elapsed_s = round(time.time() - started, 2)
    _emit(on_event, "done",
          f"Done in {report.elapsed_s}s using {report.searches_used} SerpApi searches.")
    return report
