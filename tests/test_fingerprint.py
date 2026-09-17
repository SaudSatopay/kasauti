from kasauti.fingerprint import fingerprint


def test_clean_message_scores_low():
    fp = fingerprint("Lunch at 1pm tomorrow? Let me know if that works for you.")
    assert fp.score < 25
    assert fp.level == "low"


def test_classic_chain_forward_scores_high():
    text = (
        "URGENT!! 🙏🙏🙏 Forward this to 10 groups IMMEDIATELY before it is deleted!! "
        "Media won't show you this!! Scientists say this cures cancer 100%!! "
        "FREE recharge for everyone, click this link now!!! 🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉"
    )
    fp = fingerprint(text)
    assert fp.score >= 55
    assert fp.level == "high"
    ids = {s.id for s in fp.signals}
    assert "forward_plea" in ids
    assert "deletion_threat" in ids
    assert "too_good" in ids


def test_hinglish_markers_detected():
    fp = fingerprint("Yeh message har group me bhejo, jaldi karo! Turant share karo sab ko.")
    ids = {s.id for s in fp.signals}
    assert "forward_plea" in ids


def test_hindi_devanagari_markers_detected():
    fp = fingerprint("तुरंत शेयर करें! मीडिया नहीं दिखाएगा। जल्दी शेयर करो।")
    ids = {s.id for s in fp.signals}
    assert "urgency" in ids or "forward_plea" in ids


def test_miracle_cure_detected():
    fp = fingerprint("Hot lemon water cures cancer, no side effects, doctors hide this truth")
    ids = {s.id for s in fp.signals}
    assert "miracle_cure" in ids


def test_all_caps_shouting():
    fp = fingerprint(
        "BREAKING NEWS EVERYONE MUST READ THIS RIGHT NOW THIS IS VERY IMPORTANT INDIA"
    )
    ids = {s.id for s in fp.signals}
    assert "all_caps" in ids or "heavy_caps" in ids


def test_empty_text():
    fp = fingerprint("")
    assert fp.score == 0
    assert fp.signals == []
