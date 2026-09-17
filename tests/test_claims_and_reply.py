from kasauti.claims import extract_claims, max_claims_setting
from kasauti.llm import LLM, _extract_json, resolve_config
from kasauti.models import Report, VerdictLabel
from kasauti.reply import suggest_reply


def test_no_llm_resolves_to_none():
    assert resolve_config() is None  # KASAUTI_NO_LLM=1 in conftest


def test_claims_fallback_without_llm():
    text = "Forwarded as received: UNESCO declared Indian anthem best!! https://spam.example"
    extraction = extract_claims(text, llm=LLM())
    assert extraction.llm_used is False
    assert len(extraction.claims) == 1
    claim = extraction.claims[0]
    assert claim.id == "C1"
    assert "http" not in claim.queries[0]           # URLs stripped
    assert "forwarded as received" not in claim.text_en.lower()
    assert 1 <= len(claim.queries) <= 2


def test_max_claims_env(monkeypatch):
    monkeypatch.setenv("KASAUTI_MAX_CLAIMS", "9")
    assert max_claims_setting() == 4  # hard cap
    monkeypatch.setenv("KASAUTI_MAX_CLAIMS", "junk")
    assert max_claims_setting() == 2  # default
    monkeypatch.setenv("KASAUTI_MAX_CLAIMS", "1")
    assert max_claims_setting() == 1


def test_extract_json_variants():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('prose before {"a": {"b": 2}} prose after') == {"a": {"b": 2}}
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


def _report(label: VerdictLabel, lang: str = "en") -> Report:
    return Report(
        input_text="test forward",
        language=lang,
        overall_label=label,
        overall_confidence=0.7,
    )


def test_fallback_reply_english_false():
    reply, lang = suggest_reply(_report(VerdictLabel.FALSE), llm=LLM())
    assert lang == "en"
    assert "false" in reply.lower()


def test_fallback_reply_hindi():
    reply, lang = suggest_reply(_report(VerdictLabel.FALSE, lang="hi"), llm=LLM())
    assert lang == "hi"
    assert "galat" in reply.lower() or "फर्जी" in reply


def test_fallback_reply_never_empty_for_any_label():
    for label in VerdictLabel:
        reply, _ = suggest_reply(_report(label), llm=LLM())
        assert reply.strip()
