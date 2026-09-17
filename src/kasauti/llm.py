"""Provider-agnostic LLM layer.

Kasauti talks to any OpenAI-compatible chat endpoint through one tiny wrapper,
so users can bring whichever key they already have — or none at all:

  OPENAI_API_KEY      → api.openai.com          (gpt-4o-mini)
  GEMINI_API_KEY      → Gemini OpenAI-compat    (gemini-2.5-flash, free tier)
  ANTHROPIC_API_KEY   → Anthropic OpenAI-compat (claude-haiku-4-5)
  GROQ_API_KEY        → Groq                    (llama-3.3-70b-versatile)
  KASAUTI_OLLAMA_MODEL→ local Ollama            (fully offline & free)

Explicit override always wins: KASAUTI_LLM_BASE_URL / _API_KEY / _MODEL.
If nothing is configured, Kasauti degrades gracefully to rule-based mode.
"""
from __future__ import annotations

import json
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    provider: str
    # Extra params merged into every request body (via the OpenAI SDK's
    # extra_body). Used to disable Gemini's thinking mode, which otherwise
    # adds 30–60s of latency per call and causes silent timeout fallbacks.
    extra_params: dict[str, Any] = field(default_factory=dict)


def _gemini_extra() -> dict[str, Any]:
    """reasoning_effort='none' turns off 2.5-flash thinking → ~2s calls.
    Overridable via KASAUTI_GEMINI_THINKING (none|low|medium|high)."""
    effort = os.getenv("KASAUTI_GEMINI_THINKING", "none").strip().lower()
    return {"reasoning_effort": effort} if effort in {"none", "low", "medium", "high"} else {}


def _is_gemini(base_url: str) -> bool:
    return "generativelanguage.googleapis.com" in base_url


_AUTO_PROVIDERS: list[tuple[str, str, str, str]] = [
    # (env var, base_url, default model, provider name)
    ("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini", "OpenAI"),
    (
        "GEMINI_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-flash",
        "Google Gemini",
    ),
    (
        "GOOGLE_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-flash",
        "Google Gemini",
    ),
    ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1/", "claude-haiku-4-5", "Anthropic"),
    ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "Groq"),
]


def resolve_config() -> Optional[LLMConfig]:
    """Figure out which LLM to use from the environment. None → rule-based mode."""
    if os.getenv("KASAUTI_NO_LLM", "").strip() in {"1", "true", "yes"}:
        return None

    base = os.getenv("KASAUTI_LLM_BASE_URL", "").strip()
    key = os.getenv("KASAUTI_LLM_API_KEY", "").strip()
    model = os.getenv("KASAUTI_LLM_MODEL", "").strip()
    if base and model:
        return LLMConfig(
            base_url=base, api_key=key or "not-needed", model=model, provider="custom",
            extra_params=_gemini_extra() if _is_gemini(base) else {},
        )

    for env, url, default_model, provider in _AUTO_PROVIDERS:
        value = os.getenv(env, "").strip()
        if value:
            return LLMConfig(
                base_url=url, api_key=value, model=model or default_model, provider=provider,
                extra_params=_gemini_extra() if _is_gemini(url) else {},
            )

    ollama_model = os.getenv("KASAUTI_OLLAMA_MODEL", "").strip()
    if ollama_model:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        return LLMConfig(
            base_url=f"{host}/v1", api_key="ollama", model=ollama_model, provider="Ollama (local)"
        )
    return None


def _extract_json(raw: str) -> Optional[dict[str, Any]]:
    """Pull the first JSON object out of an LLM reply, fences and all."""
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start = raw.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(raw[start : i + 1])
                    break
    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def _llm_cache_ttl_seconds() -> int:
    try:
        hours = float(os.getenv("KASAUTI_LLM_CACHE_TTL_HOURS", "48"))
    except ValueError:
        hours = 48.0
    return int(hours * 3600)


class LLM:
    """Minimal chat-JSON client over the `openai` SDK.

    Successful responses are cached on disk (keyed on model + prompt + params).
    This keeps a warm demo instant and, crucially on free tiers, avoids
    re-spending the per-minute request quota when the same forward is re-checked.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or resolve_config()
        self._client = None
        self._cache_dir = Path(os.getenv("KASAUTI_CACHE_DIR", ".kasauti_cache")) / "llm"
        if self.config is not None:
            try:
                from openai import OpenAI  # lazy import

                self._client = OpenAI(
                    base_url=self.config.base_url,
                    api_key=self.config.api_key,
                    timeout=float(os.getenv("KASAUTI_LLM_TIMEOUT", "45")),
                    max_retries=1,
                )
            except Exception:  # pragma: no cover - missing dep / bad env
                self._client = None
                self.config = None

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def provider(self) -> Optional[str]:
        return f"{self.config.provider} · {self.config.model}" if self.config else None

    def _cache_key(self, system: str, user: str, temperature: float, max_tokens: int) -> Path:
        payload = json.dumps(
            {
                "m": self.config.model if self.config else "",
                "s": system, "u": user, "t": temperature, "n": max_tokens,
                "x": self.config.extra_params if self.config else {},
            },
            sort_keys=True, ensure_ascii=False,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return self._cache_dir / f"{digest}.json"

    def _cache_get(self, path: Path) -> Optional[dict[str, Any]]:
        ttl = _llm_cache_ttl_seconds()
        if ttl <= 0 or not path.exists():
            return None
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(blob.get("ts", 0)) > ttl:
                return None
            return blob.get("data")
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def _cache_put(self, path: Path, data: dict[str, Any]) -> None:
        if _llm_cache_ttl_seconds() <= 0:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False),
                            encoding="utf-8")
        except OSError:
            pass

    def chat_json(
        self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 1200
    ) -> Optional[dict[str, Any]]:
        """One JSON-returning chat call; one retry with a stern reminder.

        Cached on disk: a repeated identical call returns instantly and spends
        no request quota (important on rate-limited free tiers)."""
        if not self._client or not self.config:
            return None

        cache_path = self._cache_key(system, user, temperature, max_tokens)
        cached = self._cache_get(cache_path)
        if cached is not None:
            return cached

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        # extra_params (e.g. reasoning_effort) help some models but are rejected
        # by others with a 400; _use_extra flips off and retries if that happens.
        self._use_extra = bool(self.config.extra_params)
        for attempt in range(2):
            raw = self._create(messages, temperature, max_tokens)
            if raw is None:
                return None
            data = _extract_json(raw)
            if data is not None:
                self._cache_put(cache_path, data)
                return data
            messages.append({"role": "assistant", "content": raw[:2000]})
            messages.append({
                "role": "user",
                "content": "Reply again with ONLY a valid JSON object. No prose, no markdown.",
            })
        return None

    def _create(self, messages: list, temperature: float, max_tokens: int) -> Optional[str]:
        """One completion call. On a 400 that looks like a rejected extra param,
        retry once without extra_body; on any other error, give up (→ fallback)."""
        extra = self.config.extra_params if getattr(self, "_use_extra", False) else None
        try:
            resp = self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra or None,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            if extra and "400" in str(exc):
                self._use_extra = False  # this model dislikes the extra param
                try:
                    resp = self._client.chat.completions.create(
                        model=self.config.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return (resp.choices[0].message.content or "").strip()
                except Exception:
                    return None
            return None
