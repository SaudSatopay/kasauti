"""The 'Reply to the group' generator.

Knowing a forward is fake is half the battle; the other half is telling your
family group without starting a fight. Kasauti drafts a short, warm,
non-preachy correction in the same language as the forward, with receipts.
"""
from __future__ import annotations

from typing import Optional

from .llm import LLM
from .models import Report, VerdictLabel

_SYSTEM = """You write WhatsApp replies for Kasauti, a misinformation checker used in Indian
family and community groups. Given a checked forward and its verdict, draft ONE short reply
the user can paste into the group.

Tone: warm, respectful, zero lecturing, zero sarcasm — you are correcting your own uncle,
not winning a debate. Max 75 words. At most one emoji (🙏 works). Include the 1-2 most
credible links provided. Never shame the sender; blame the message ("yeh message purana hai"),
never the person.

Write in the language given as reply_language (e.g. Hinglish written in Latin script, Hindi in
Devanagari, or English). Return ONLY JSON: {"reply": "<the message>"}"""

_FALLBACK_EN = {
    VerdictLabel.FALSE: "🙏 I looked this up — fact-checkers have found this message to be false. Sharing what I found: {links}. Better not to forward it further.",
    VerdictLabel.MISLEADING: "🙏 Checked this one — it mixes some truth with wrong details: {links}. Worth reading before forwarding.",
    VerdictLabel.OUTDATED: "🙏 Small update — this is an old story being re-shared as new: {links}. Not current news.",
    VerdictLabel.SATIRE: "🙂 This one is actually from a satire/comedy page, not real news: {links}.",
    VerdictLabel.UNVERIFIED: "🙏 I tried verifying this and couldn't find any reliable source reporting it: {links}. Maybe let's wait before forwarding.",
    VerdictLabel.TRUE: "Checked this — it appears to be genuine: {links}.",
    VerdictLabel.MOSTLY_TRUE: "Checked this — it's largely accurate, details here: {links}.",
}

_FALLBACK_HI = {
    VerdictLabel.FALSE: "🙏 Maine yeh check kiya — fact-checkers ke मुताबिक yeh message galat hai: {links}. Aage forward na karein toh behtar hai.",
    VerdictLabel.MISLEADING: "🙏 Yeh message aadha sach, aadha galat hai — details yahan: {links}. Forward karne se pehle ek baar padh lein.",
    VerdictLabel.OUTDATED: "🙏 Yeh purani khabar hai jo nayi bana kar bheji ja rahi hai: {links}.",
    VerdictLabel.SATIRE: "🙂 Yeh asli khabar nahi, ek comedy/satire page ka post hai: {links}.",
    VerdictLabel.UNVERIFIED: "🙏 Maine check kiya, kisi bharosemand source ne yeh khabar report nahi ki hai: {links}. Thoda ruk kar confirm kar lete hain.",
    VerdictLabel.TRUE: "Maine check kiya — yeh khabar sahi lag rahi hai: {links}.",
    VerdictLabel.MOSTLY_TRUE: "Yeh khabar kaafi had tak sahi hai, details: {links}.",
}


def _top_links(report: Report, limit: int = 2) -> list[str]:
    cited: list[str] = []
    for v in report.verdicts:
        cited.extend(v.citation_ids)
    ranked = []
    seen = set()
    for eid in cited:
        item = report.evidence_by_id(eid)
        if item and item.link not in seen:
            ranked.append(item)
            seen.add(item.link)
    if not ranked:
        ranked = sorted(report.evidence, key=lambda e: e.score, reverse=True)
    return [e.link for e in ranked[:limit]]


_UNVERIFIED_NO_LINKS = {
    "en": ("🙏 I tried verifying this and couldn't find any reliable source "
           "reporting it yet. Maybe let's wait before forwarding."),
    "hi": ("🙏 Maine check kiya, abhi tak kisi bharosemand source ne yeh khabar "
           "report nahi ki hai. Thoda ruk kar confirm kar lete hain."),
}


def _fallback_reply(report: Report, lang: str) -> str:
    hindi = lang.startswith("hi")
    # For an unverified forward there is no debunk to link; attaching the
    # top-ranked-but-uncommitted results would only lend it false authority.
    if report.overall_label == VerdictLabel.UNVERIFIED:
        return _UNVERIFIED_NO_LINKS["hi" if hindi else "en"]
    table = _FALLBACK_HI if hindi else _FALLBACK_EN
    template = table.get(report.overall_label, table[VerdictLabel.UNVERIFIED])
    links = " ".join(_top_links(report)) or "(no reliable links found)"
    return template.format(links=links)


def suggest_reply(report: Report, *, llm: Optional[LLM] = None,
                  reply_language: Optional[str] = None) -> tuple[str, str]:
    """Return (reply_text, language_code_used)."""
    llm = llm or LLM()
    lang = (reply_language or report.language or "en").strip() or "en"

    if not llm.available:
        return _fallback_reply(report, lang), lang

    links = _top_links(report)
    verdict_lines = "\n".join(
        f"- {v.claim_id}: {v.label.display} (confidence {v.confidence:.0%}) — {v.rationale}"
        for v in report.verdicts
    )
    user = (
        f"ORIGINAL FORWARD:\n{report.input_text[:800]}\n\n"
        f"OVERALL VERDICT: {report.overall_label.display} "
        f"(confidence {report.overall_confidence:.0%})\n"
        f"PER-CLAIM:\n{verdict_lines or '- (none)'}\n\n"
        f"LINKS TO INCLUDE: {', '.join(links) if links else '(none found)'}\n"
        f"reply_language: {lang} "
        f"({report.language_name})"
    )
    data = llm.chat_json(_SYSTEM, user, temperature=0.5, max_tokens=300)
    if data and str(data.get("reply") or "").strip():
        return str(data["reply"]).strip()[:600], lang
    return _fallback_reply(report, lang), lang
