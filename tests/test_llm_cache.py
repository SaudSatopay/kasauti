"""Disk cache for LLM responses (keeps demos instant, saves free-tier quota)."""
from kasauti.llm import LLM, LLMConfig


def _llm(tmp_path, monkeypatch, ttl="48"):
    monkeypatch.setenv("KASAUTI_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("KASAUTI_LLM_CACHE_TTL_HOURS", ttl)
    cfg = LLMConfig(base_url="https://example.test/v1", api_key="k",
                    model="test-model", provider="test")
    return LLM(config=cfg)


def test_cache_round_trip(tmp_path, monkeypatch):
    llm = _llm(tmp_path, monkeypatch)
    path = llm._cache_key("sys", "user", 0.2, 1200)
    assert llm._cache_get(path) is None          # cold
    llm._cache_put(path, {"label": "false"})
    assert llm._cache_get(path) == {"label": "false"}  # warm


def test_cache_key_depends_on_prompt(tmp_path, monkeypatch):
    llm = _llm(tmp_path, monkeypatch)
    a = llm._cache_key("sys", "user A", 0.2, 1200)
    b = llm._cache_key("sys", "user B", 0.2, 1200)
    assert a != b


def test_cache_key_depends_on_extra_params(tmp_path, monkeypatch):
    llm = _llm(tmp_path, monkeypatch)
    base = llm._cache_key("sys", "user", 0.2, 1200)
    llm.config.extra_params = {"reasoning_effort": "high"}
    assert llm._cache_key("sys", "user", 0.2, 1200) != base


def test_cache_disabled_with_zero_ttl(tmp_path, monkeypatch):
    llm = _llm(tmp_path, monkeypatch, ttl="0")
    path = llm._cache_key("sys", "user", 0.2, 1200)
    llm._cache_put(path, {"x": 1})
    assert llm._cache_get(path) is None
