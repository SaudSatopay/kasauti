"""Provider resolution and Gemini thinking-mode control."""
from kasauti.llm import _gemini_extra, _is_gemini, resolve_config

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def test_is_gemini():
    assert _is_gemini(GEMINI_URL)
    assert not _is_gemini("https://api.openai.com/v1")


def test_gemini_thinking_off_by_default(monkeypatch):
    monkeypatch.delenv("KASAUTI_GEMINI_THINKING", raising=False)
    assert _gemini_extra() == {"reasoning_effort": "none"}


def test_gemini_thinking_override(monkeypatch):
    monkeypatch.setenv("KASAUTI_GEMINI_THINKING", "low")
    assert _gemini_extra() == {"reasoning_effort": "low"}
    monkeypatch.setenv("KASAUTI_GEMINI_THINKING", "garbage")
    assert _gemini_extra() == {}


def test_gemini_config_disables_thinking(monkeypatch):
    monkeypatch.delenv("KASAUTI_NO_LLM", raising=False)
    monkeypatch.delenv("KASAUTI_GEMINI_THINKING", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    cfg = resolve_config()
    assert cfg is not None
    assert cfg.provider == "Google Gemini"
    assert cfg.extra_params == {"reasoning_effort": "none"}


def test_openai_config_has_no_thinking_param(monkeypatch):
    monkeypatch.delenv("KASAUTI_NO_LLM", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cfg = resolve_config()
    assert cfg is not None
    assert cfg.provider == "OpenAI"
    assert cfg.extra_params == {}  # never send reasoning_effort to a non-reasoning model
