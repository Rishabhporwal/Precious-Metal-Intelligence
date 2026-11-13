"""OpenRouter LLM client with a hard Redis cache (cost control).

Cache design (user-mandated cost saving):
- key = llm:{model}:{sha256(model + prompt_version + messages)}
- value = full response JSON, TTL from env (default 12h)
- every call reports cache HIT/MISS so cost is observable
- misses after failure never fabricate: errors raise and callers fall back
  to deterministic narratives flagged as such.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from functools import lru_cache

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger("llm")

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-chat"  # $0.26/M in, $1.03/M out — cheap, capable


class LLMConfig:
    def __init__(self, env: dict[str, str] | None = None):
        env = env or os.environ
        self.api_key = env.get("LLM_API_KEY") or None
        self.model = env.get("LLM_MODEL") or DEFAULT_MODEL
        self.prompt_version = env.get("LLM_PROMPT_VERSION") or "p7-1.0"
        # Host-run tooling prefers the host-mapped URL (same precedence as app/db).
        self.redis_url = env.get("REDIS_URL_HOST") or env.get("REDIS_URL") or "redis://localhost:6379/0"
        self.cache_ttl = int(env.get("LLM_CACHE_TTL_SECONDS", str(12 * 3600)))
        self.timeout_s = float(env.get("LLM_TIMEOUT_SECONDS", "90"))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@lru_cache
def _redis(url: str):
    return aioredis.from_url(url, decode_responses=True)


async def close_llm_cache() -> None:
    pass  # redis client is cached per-process; connections reap on shutdown


def cache_key_for(messages: list[dict], cfg: LLMConfig | None = None) -> str:
    """The exact cache key chat() uses — lets callers invalidate poisoned entries."""
    cfg = cfg or LLMConfig()
    return "llm:" + hashlib.sha256(
        (cfg.model + "|" + cfg.prompt_version + "|" + json.dumps(messages, sort_keys=True)).encode()
    ).hexdigest()


async def invalidate_cache(messages: list[dict], cfg: LLMConfig | None = None) -> None:
    cfg = cfg or LLMConfig()
    try:
        redis = _redis(cfg.redis_url)
        await redis.delete(cache_key_for(messages, cfg))
    except Exception:  # noqa: BLE001
        pass


async def _chat_once(messages: list[dict], cfg: LLMConfig, max_tokens: int) -> dict:
    """Single chat completion with Redis cache. Returns {content, model, usage, cache_hit}.

    validate: optional callable(result) -> str|None — return a reason string to reject
    the response (cached or fresh); the cache entry is deleted and the call retried live.
    Guards against poisoned entries like valid-JSON-but-empty '[]'.
    """
    """Single chat completion with Redis cache. Returns {content, model, usage, cache_hit}."""
    cfg = cfg or LLMConfig()
    if not cfg.configured:
        raise RuntimeError("LLM_API_KEY is not set — LLM calls unavailable")

    cache_key = "llm:" + hashlib.sha256(
        (cfg.model + "|" + cfg.prompt_version + "|" + json.dumps(messages, sort_keys=True)).encode()
    ).hexdigest()

    redis = _redis(cfg.redis_url)
    try:
        cached = await redis.get(cache_key)
        if cached:
            payload = json.loads(cached)
            if payload.get("content"):  # poisoned-cache guard: never return empty content
                payload["cache_hit"] = True
                logger.info("LLM cache HIT (%s), cost avoided", cfg.model)
                return payload
            logger.warning("LLM cache had empty content — ignoring poisoned entry, calling live")
    except Exception as exc:  # noqa: BLE001 — cache problems degrade, never block
        logger.warning("LLM cache read failed: %s", exc)

    body = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=cfg.timeout_s) as client:
        resp = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
            json=body,
        )
        # Low-balance accounts: OpenRouter pre-authorizes max_tokens × price and
        # returns 402 with the affordable budget. Retry ONCE at that budget, then
        # once more on a FREE model (zero cost) so the pipeline never hard-stops.
        if resp.status_code == 402:
            m = re.search(r"can only afford (\d+)", resp.text)
            if m and int(m.group(1)) >= 200:
                body["max_tokens"] = int(int(m.group(1)) * 0.9)
                logger.warning("LLM 402 — retrying with max_tokens=%s (low balance)", body["max_tokens"])
                resp = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
                    json=body,
                )
        if resp.status_code in (402, 429):
            # rotate through free models (zero cost, separate rate-limit pools)
            fallback_models = [
                os.environ.get("LLM_FALLBACK_MODEL", "google/gemma-4-31b-it:free"),
                "nvidia/nemotron-3.5-lightning:free",
                "google/gemma-4-26b-a4b-it:free",
            ]
            for fm in fallback_models:
                if fm == body["model"]:
                    continue
                body["model"] = fm
                logger.warning("LLM %s — falling back to free model %s", resp.status_code, fm)
                resp = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"},
                    json=body,
                )
                if resp.status_code == 200:
                    try:
                        if resp.json().get("choices", [{}])[0].get("message", {}).get("content"):
                            break  # usable content — accept this model
                    except Exception:  # noqa: BLE001
                        pass
                    # empty content — rotate to the next free model
    if resp.status_code == 401:
        raise RuntimeError("OpenRouter rejected the API key")
    if resp.status_code == 429:
        raise RuntimeError("OpenRouter rate limit reached")
    resp.raise_for_status()
    data = resp.json()
    if "choices" not in data:
        raise RuntimeError(f"OpenRouter unexpected response: {json.dumps(data)[:200]}")

    content = data["choices"][0]["message"].get("content")
    if not content:
        raise RuntimeError("LLM returned empty content (all fallbacks exhausted)")
    payload = {
        "content": content,
        "model": data.get("model", cfg.model),
        "usage": data.get("usage", {}),
        "cache_hit": False,
    }
    try:
        await redis.set(cache_key, json.dumps(payload), ex=cfg.cache_ttl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM cache write failed: %s", exc)
    logger.info("LLM cache MISS (%s), usage=%s", cfg.model, payload.get("usage"))
    return payload


async def chat(messages: list[dict], cfg: LLMConfig | None = None, max_tokens: int = 1200,
               validate=None) -> dict:
    """chat() with poisoned-response rejection: if validate() rejects, the cache
    entry is deleted and the call retried live (once)."""
    cfg = cfg or LLMConfig()
    result = await _chat_once(messages, cfg, max_tokens)
    if validate is None:
        return result
    reason = None
    try:
        reason = validate(result)
    except Exception:  # noqa: BLE001 — a broken validator must not break the call
        reason = None
    if reason:
        logger.warning("LLM response rejected (%s) — invalidating cache, retrying live", reason)
        await invalidate_cache(messages, cfg)
        result = await _chat_once(messages, cfg, max_tokens)
        r2 = None
        try:
            r2 = validate(result)
        except Exception:  # noqa: BLE001
            r2 = None
        if r2:
            raise RuntimeError(f"LLM response invalid after retry: {r2}")
    return result
