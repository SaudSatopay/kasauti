"""SerpApi access layer.

Every piece of outside evidence Kasauti uses flows through this module, via
four retrieval strategies on three SerpApi engines:

  1. `google`       — organic web results for each claim (gl=in)
  2. `google_news`  — current news coverage for each claim
  3. `google`       — a targeted `site:` sweep across Indian fact-check desks
  4. `google_lens`  — reverse image search for attached photos

Extras that matter for a free-tier key (250 searches/month):
  * a transparent per-run search budget counter (surfaced in every report),
  * an on-disk response cache (default 22 h TTL) so iterating on the same
    forward during development costs zero credits,
  * an offline fixtures mode used by the test suite — tests never hit the
    network and never spend a credit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from importlib import resources
from pathlib import Path
from typing import Any, Optional


class KasautiError(RuntimeError):
    """User-facing error with a helpful message."""


def _cache_ttl_seconds() -> int:
    try:
        hours = float(os.getenv("KASAUTI_CACHE_TTL_HOURS", "22"))
    except ValueError:
        hours = 22.0
    return int(hours * 3600)


def _slug_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


class SerpSearcher:
    """Thin, budget-aware wrapper around the official `serpapi` client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        offline: Optional[bool] = None,
        cache_dir: Optional[str] = None,
    ):
        self.offline = (
            offline
            if offline is not None
            else os.getenv("KASAUTI_OFFLINE", "").strip() in {"1", "true", "yes"}
        )
        self.api_key = (
            api_key
            or os.getenv("SERPAPI_API_KEY", "").strip()
            or os.getenv("SERPAPI_KEY", "").strip()
        )
        self.searches_used = 0
        self.cache_hits = 0
        self._cache_dir = Path(cache_dir or ".kasauti_cache")
        self._client = None
        self._fixtures: Optional[list[dict[str, Any]]] = None

        if not self.offline:
            if not self.api_key:
                raise KasautiError(
                    "No SerpApi key found. Set SERPAPI_API_KEY in your environment or .env "
                    "file — a free key (250 searches/month) is available at "
                    "https://serpapi.com/manage-api-key . "
                    "Or run with --offline to try the bundled demo fixtures."
                )
            import serpapi  # lazy import so offline mode has zero requirements

            self._client = serpapi.Client(api_key=self.api_key, timeout=25)

    # ── low-level ────────────────────────────────────────────────────────

    def _cache_path(self, params: dict[str, Any]) -> Path:
        payload = json.dumps(params, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return self._cache_dir / f"{params.get('engine', 'x')}_{digest}.json"

    def _from_cache(self, params: dict[str, Any]) -> Optional[dict[str, Any]]:
        ttl = _cache_ttl_seconds()
        if ttl <= 0:
            return None
        path = self._cache_path(params)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(blob.get("ts", 0)) > ttl:
                return None
            self.cache_hits += 1
            return blob.get("data")
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def _to_cache(self, params: dict[str, Any], data: dict[str, Any]) -> None:
        if _cache_ttl_seconds() <= 0:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path(params).write_text(
                json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass  # cache is best-effort

    def _load_fixtures(self) -> list[dict[str, Any]]:
        if self._fixtures is None:
            fixtures: list[dict[str, Any]] = []
            try:
                root = resources.files("kasauti").joinpath("fixtures")
                for entry in root.iterdir():
                    if entry.name.endswith(".json"):
                        try:
                            fixtures.append(json.loads(entry.read_text(encoding="utf-8")))
                        except json.JSONDecodeError:
                            continue
            except (FileNotFoundError, ModuleNotFoundError):
                pass
            self._fixtures = fixtures
        return self._fixtures

    def _from_fixtures(self, params: dict[str, Any]) -> dict[str, Any]:
        """Best keyword-overlap match among bundled fixtures for this engine."""
        engine = params.get("engine", "google")
        query_tokens = _slug_tokens(str(params.get("q") or params.get("url") or ""))
        best: tuple[float, int, dict[str, Any]] | None = None
        for fx in self._load_fixtures():
            if fx.get("_engine") != engine:
                continue
            match_tokens = set(fx.get("_match", []))
            overlap = len(query_tokens & match_tokens)
            score = overlap / max(len(match_tokens), 1) if match_tokens else 0.0
            # Ties broken by absolute overlap, so the more specific fixture wins.
            if overlap >= 2 and (best is None or (score, overlap) > (best[0], best[1])):
                best = (score, overlap, fx)
        if best:
            return best[2].get("data", {})
        return {}

    def _run(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.offline:
            self.searches_used += 1  # counted so budget maths stay honest
            return self._from_fixtures(params)

        cached = self._from_cache(params)
        if cached is not None:
            return cached

        import serpapi

        try:
            results = self._client.search(params)  # type: ignore[union-attr]
        except serpapi.HTTPError as exc:  # pragma: no cover - needs live API
            status = getattr(exc, "status_code", None)
            if status == 401:
                raise KasautiError(
                    "SerpApi rejected the API key (401). Check SERPAPI_API_KEY."
                ) from exc
            if status == 429:
                raise KasautiError(
                    "SerpApi rate/plan limit reached (429). The free plan includes "
                    "250 searches/month — see https://serpapi.com/pricing ."
                ) from exc
            raise KasautiError(f"SerpApi request failed ({status}): {exc}") from exc
        except Exception as exc:  # pragma: no cover - timeouts etc.
            raise KasautiError(f"SerpApi request failed: {exc}") from exc

        self.searches_used += 1
        data = dict(results)
        self._to_cache(params, data)
        return data

    # ── retrieval strategies ─────────────────────────────────────────────

    def web(self, query: str, *, hl: str = "en", num: int = 10) -> dict[str, Any]:
        """Strategy 1 — organic Google results, India-localised."""
        return self._run({
            "engine": "google",
            "q": query,
            "google_domain": "google.co.in",
            "gl": "in",
            "hl": hl,
            "num": num,
        })

    def news(self, query: str, *, hl: str = "en") -> dict[str, Any]:
        """Strategy 2 — Google News coverage."""
        return self._run({
            "engine": "google_news",
            "q": query,
            "gl": "in",
            "hl": hl,
        })

    def factcheck_sweep(self, query: str) -> dict[str, Any]:
        """Strategy 3 — one query swept across major Indian fact-check desks."""
        from .sources import factcheck_sweep_query

        return self._run({
            "engine": "google",
            "q": factcheck_sweep_query(query),
            "google_domain": "google.co.in",
            "gl": "in",
            "hl": "en",
            "num": 10,
        })

    def lens(self, image_url: str) -> dict[str, Any]:
        """Strategy 4 — Google Lens reverse image search."""
        return self._run({
            "engine": "google_lens",
            "url": image_url,
            "type": "all",
            "hl": "en",
            "country": "in",
        })
