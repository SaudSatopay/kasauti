"""Test config: everything runs offline, no LLM, no network, zero credits."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KASAUTI_OFFLINE", "1")
    monkeypatch.setenv("KASAUTI_NO_LLM", "1")
    monkeypatch.setenv("KASAUTI_CACHE_TTL_HOURS", "0")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("KASAUTI_OLLAMA_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
