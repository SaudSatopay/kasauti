"""Forward Fingerprint — deterministic chain-forward heuristics.

Before any API call, Kasauti scores how much a message *smells* like a viral
chain forward: forwarding pleas, urgency, deletion threats, vague authority,
too-good-to-be-true offers, miracle cures, SHOUTING, emoji storms.

This is intentionally not an LLM: it is instant, free, explainable, and it
works offline. The score never decides a verdict by itself — it only tells the
user (and the verdict prompt) that the message carries the classic markers of
manufactured virality. Patterns cover English, Hinglish and Hindi (Devanagari).
"""
from __future__ import annotations

import re

from .models import Fingerprint, FingerprintSignal

_FLAGS = re.IGNORECASE | re.UNICODE

# (id, label, weight, patterns, explanation)
_RULES: list[tuple[str, str, int, list[str], str]] = [
    (
        "forward_plea",
        "Begs to be forwarded",
        22,
        [
            r"\bforward (this|it|to|kare?in|karo|kijiye)\b",
            r"\bshare (this|it|to|karo|kare?in|kijiye|maximum|with every)\b",
            r"\bsend (this )?to (all|every|10|everyone)\b",
            r"\b(10|20|5) (logo|logon|groups?|people|friends)\b.{0,20}\b(bhej|send|share|forward)",
            r"\b(bhejo|bhejein|bhej do|aage bhejo|circulate|पास करें|आगे भेज)",
            r"जल्दी\s*(से)?\s*(शेयर|भेज|फॉरवर्ड)",
            r"\bhar (group|whatsapp) (me|mein)\b",
            r"\bdo not stop (this|the) message\b",
        ],
        "Genuine news never begs to be forwarded. Chain messages do.",
    ),
    (
        "urgency",
        "Manufactured urgency",
        12,
        [
            r"\burgent(ly)?\b",
            r"\bbreaking\b",
            r"\bimmediately\b",
            r"\bturant\b",
            r"\babhi (ke abhi|turant|share)\b",
            r"तुरंत|अभी\s*तुरंत|आपातकाल",
            r"\bemergency alert\b",
            r"\blast (day|date|chance) (to|for)\b",
        ],
        "Urgency is used to make you forward before you think.",
    ),
    (
        "deletion_threat",
        "'Will be deleted' / 'media is hiding it'",
        18,
        [
            r"before (it('| i)?s|this is|it gets) (deleted|removed|taken down)",
            r"delete (kar|ho) (diya|jayega|jaayega)",
            r"\bmedia (won'?t|will not|is not|doesn'?t) (show|cover|tell)\b",
            r"\bmedia is hiding\b",
            r"\bnews channels? (won'?t|hiding|will never)\b",
            r"मीडिया (नहीं दिखाएगा|छुपा रही)",
            r"\bwhatsapp (will be|is getting) (closed|banned)\b",
            r"\bthey don'?t want you to know\b",
        ],
        "Claiming suppression ('media won't show this') is a classic hoax marker.",
    ),
    (
        "vague_authority",
        "Vague authority, no source",
        14,
        [
            r"\b(a |an |one )?(top |senior |famous )?(scientists?|doctors?|experts?) (say|says|said|have (found|warned)|warn)\b",
            r"\b(IIT|AIIMS|NASA|WHO|UNESCO|ICMR|UN)\b.{0,40}\b(says?|said|declared|confirmed|study|research|warning)\b",
            r"\bgovernment (has )?(announced|declared|decided)\b",
            r"\bofficial (news|announcement|circular)\b",
            r"(वैज्ञानिकों|डॉक्टरों) (ने|का) (कहा|दावा)",
            r"\bforwarded as received\b",
        ],
        "Real announcements name the person, date and document — not just 'scientists say'.",
    ),
    (
        "too_good",
        "Too good to be true",
        20,
        [
            r"\bfree (recharge|laptop|mobile|data|petrol|scooty|iphone)\b",
            r"\b(won|win|jeeto?)\b.{0,30}\b(lottery|lucky draw|prize)\b",
            r"₹\s?\d[\d,]*\s?(lakh|crore|लाख|करोड़)?.{0,30}\b(free|prize|lottery|gift|jeet)",
            r"\b(modi|sarkar|govt|government)\b.{0,30}\b(de (raha|rahi)|giving|free (me|mein)?)\b",
            r"\bclick (this|the|below) link\b",
            r"\bregister (now|karo|kare)\b.{0,30}\b(free|gift|prize)",
            r"मुफ़्त|मुफ्त (रिचार्ज|लैपटॉप|मोबाइल)",
        ],
        "Free-gift and lottery messages are the most common phishing bait in India.",
    ),
    (
        "miracle_cure",
        "Miracle-cure claims",
        18,
        [
            r"\bcures? (cancer|covid|corona|diabetes|bp|kidney|dengue)\b",
            r"\b100% (cure|effective|guaranteed|immunity)\b",
            r"\bno side ?effects?\b",
            r"\bdoctors (hide|don'?t want|never tell)\b",
            r"\bgharelu (nuskha|upay|ilaj)\b",
            r"(कैंसर|कोरोना|डायबिटीज)\s*(का)?\s*(रामबाण|इलाज|उपचार)",
            r"\bimmunity (badhaye|booster)\b.{0,30}\b(guaranteed|100)",
        ],
        "Medical misinformation spreads fastest and does the most harm.",
    ),
    (
        "chain_blessing",
        "Chain-letter superstition",
        8,
        [
            r"\b(good luck|good news) (will come|within|in \d+ (days|hours))\b",
            r"\bignore (this )?(message|at your own risk)\b",
            r"\bbad luck\b.{0,30}\b(ignore|delete|not forward)",
            r"\bदुर्भाग्य|शुभ समाचार मिलेगा",
        ],
        "Blessing/curse chains are the oldest form of forced virality.",
    ),
]

_EMOJI_RE = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF☀-➿\U0001FA70-\U0001FAFF]"
)


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha() and c.isascii()]
    if len(letters) < 40:
        return 0.0
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters)


def fingerprint(text: str) -> Fingerprint:
    """Score a message 0–100 on chain-forward markers."""
    text = text or ""
    signals: list[FingerprintSignal] = []

    for rule_id, label, weight, patterns, detail in _RULES:
        for pat in patterns:
            if re.search(pat, text, _FLAGS):
                signals.append(
                    FingerprintSignal(id=rule_id, label=label, detail=detail, weight=weight)
                )
                break  # one hit per rule

    ratio = _caps_ratio(text)
    if ratio > 0.5:
        signals.append(FingerprintSignal(
            id="all_caps", label="SHOUTING IN ALL CAPS", weight=12,
            detail="Over half the message is capitalised — a hallmark of hoax formatting.",
        ))
    elif ratio > 0.3:
        signals.append(FingerprintSignal(
            id="heavy_caps", label="Heavy use of capitals", weight=6,
            detail="Roughly a third of the message is capitalised.",
        ))

    emojis = len(_EMOJI_RE.findall(text))
    if emojis >= 10 or (len(text) > 0 and emojis / max(len(text), 1) > 0.08):
        signals.append(FingerprintSignal(
            id="emoji_storm", label="Emoji storm", weight=8,
            detail=f"{emojis} emojis — decoration standing in for evidence.",
        ))

    if re.search(r"!{3,}", text) or text.count("!") > 5:
        signals.append(FingerprintSignal(
            id="exclamation", label="Excessive exclamation", weight=5,
            detail="Multiple exclamation marks amplify emotion, not accuracy.",
        ))

    if len(text) > 220 and not re.search(r"https?://", text):
        claimy = re.search(
            r"\b(announced|declared|confirmed|reported|news|khabar|order|circular|scheme|yojana)\b",
            text, _FLAGS,
        )
        if claimy:
            signals.append(FingerprintSignal(
                id="no_source", label="Long claim, zero sources", weight=6,
                detail="Makes news-like claims but links to nothing at all.",
            ))

    score = min(100, sum(s.weight for s in signals))
    level = "high" if score >= 55 else "medium" if score >= 25 else "low"
    return Fingerprint(score=score, level=level, signals=signals)
