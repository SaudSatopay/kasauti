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
import os
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    provider: str


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
        return LLMConfig(base_url=base, api_key=key or "not-needed", model=model, provider="custom")

    for env, url, default_model, provider in _AUTO_PROVIDERS:
        value = os.getenv(env, "").strip()
        if value:
            return LLMConfig(
                base_url=url, api_key=value, model=model or default_model, provider=provider
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


class LLM:
    """Minimal chat-JSON client over the `openai` SDK."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or resolve_config()
        self._client = None
        if self.config is not None:
            try:
                from openai import OpenAI  # lazy import

                self._client = OpenAI(
                    base_url=self.config.base_url,
                    api_key=self.config.api_key,
                    timeout=60.0,
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

    def chat_json(
        self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 1200
    ) -> Optional[dict[str, Any]]:
        """One JSON-returning chat call; one retry with a stern reminder."""
        if not self._client or not self.config:
            return None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        for attempt in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                raw = (resp.choices[0].message.content or "").strip()
            except Exception:
                return None
            data = _extract_json(raw)
            if data is not None:
                return data
            messages.append({"role": "assistant", "content": raw[:2000]})
            messages.append({
                "role": "user",
                "content": "Reply again with ONLY a valid JSON object. No prose, no markdown.",
            })
        return None
