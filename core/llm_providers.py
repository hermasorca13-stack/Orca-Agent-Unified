"""
core/llm_providers.py — Multi-provider LLM support with auto-failover.

Provides:
  - AsyncLLMRouter: tries providers in order, falls back on failure.
  - get_llm_client(provider): factory for a single provider's client.

Providers supported (additive; no existing provider removed):
  - openai, anthropic, deepseek, openrouter  (already in core/agent.py)
  - gemini  (Google Generative AI)           (NEW)
  - groq    (Groq Cloud — fast Llama/Mixtral) (NEW)
  - mistral (Mistral AI)                      (NEW)
  - ollama  (local — no key needed)           (NEW)

Design principles (from BUILD_HISTORY):
  1. Add-only: never modify existing _init_llm() branches. New providers
     live here and are wired in by extending _init_llm() with ONE new branch.
  2. Lazy import: each provider is imported inside the factory so the bot
     still boots when a provider's SDK is missing.
  3. Failover: AsyncLLMRouter returns the first successful response.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------
@dataclass
class ProviderSpec:
    name: str                              # env key / provider id
    env_key: str                           # env var that holds the key
    base_url: Optional[str] = None
    default_model: str = ""
    sdk_hint: str = ""                     # which pip package to install


# Order matters: router tries left-to-right. Existing providers first.
PROVIDER_CATALOG: List[ProviderSpec] = [
    ProviderSpec("anthropic",  "ANTHROPIC_API_KEY",  default_model="claude-3-5-sonnet-20241022", sdk_hint="anthropic"),
    ProviderSpec("openai",     "OPENAI_API_KEY",     default_model="gpt-4o-mini",                sdk_hint="openai"),
    ProviderSpec("deepseek",   "DEEPSEEK_API_KEY",   base_url="https://api.deepseek.com/v1",
                  default_model="deepseek-chat",      sdk_hint="openai"),
    ProviderSpec("openrouter", "OPENROUTER_API_KEY", base_url="https://openrouter.ai/api/v1",
                  default_model="openai/gpt-4o-mini", sdk_hint="openai"),
    # --- NEW (additive) ---
    ProviderSpec("gemini",     "GEMINI_API_KEY",     base_url="https://generativelanguage.googleapis.com/v1beta",
                  default_model="gemini-2.0-flash",   sdk_hint="google-generativeai"),
    ProviderSpec("groq",       "GROQ_API_KEY",       base_url="https://api.groq.com/openai/v1",
                  default_model="llama-3.3-70b-versatile", sdk_hint="openai"),
    ProviderSpec("mistral",    "MISTRAL_API_KEY",    base_url="https://api.mistral.ai/v1",
                  default_model="mistral-small-latest",    sdk_hint="openai"),
    ProviderSpec("ollama",     "OLLAMA_HOST",        base_url="http://127.0.0.1:11434/v1",
                  default_model="llama3.2",          sdk_hint="openai"),
]


# ---------------------------------------------------------------------------
# Single-provider factory (used by existing _init_llm() extension)
# ---------------------------------------------------------------------------
def get_llm_client(provider: str, api_key: str, base_url: Optional[str] = None):
    """
    Factory for ONE provider's async client. Returns None if provider is
    unknown or the SDK is missing — caller should fall back gracefully.
    """
    p = (provider or "").lower().strip()
    if not api_key and p != "ollama":
        return None

    try:
        if p == "openai" or p in ("deepseek", "openrouter", "groq", "mistral", "ollama"):
            from openai import AsyncOpenAI
            return AsyncOpenAI(api_key=api_key or "ollama", base_url=base_url)

        if p == "anthropic":
            from anthropic import AsyncAnthropic
            return AsyncAnthropic(api_key=api_key)

        if p == "gemini":
            # Gemini has its own async client. Wrap it in a thin adapter so the
            # call site can keep using a uniform interface.
            from google import generativeai as genai
            genai.configure(api_key=api_key)
            return _GeminiAdapter(genai.GenerativeModel(
                os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            ))

    except ImportError as e:
        logger.warning(f"Provider '{p}' SDK missing: {e}. pip install {p}")
    except Exception as e:
        logger.warning(f"Provider '{p}' init failed: {e}")
    return None


class _GeminiAdapter:
    """Tiny adapter so Gemini can be called like other providers."""
    def __init__(self, model):
        self._model = model

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        # Flatten messages to a single prompt (Gemini 2 supports chat via model.start_chat)
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        prompt = (system + "\n\n" if system else "") + last_user
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: self._model.generate_content(prompt))
        return getattr(resp, "text", "")


# ---------------------------------------------------------------------------
# Auto-failover router
# ---------------------------------------------------------------------------
@dataclass
class LLMRouterResult:
    text: str
    provider: str
    model: str
    used_fallback: bool = False


class AsyncLLMRouter:
    """
    Tries a list of providers in order, returns the first success.
    Used by `agent.handle_message` when LLM_FAILOVER=1 is set.
    """

    def __init__(self, providers: List[str], env: Optional[Dict[str, str]] = None):
        self.providers = [p.lower() for p in providers]
        self._env = env or os.environ
        self._clients: Dict[str, Any] = {}

    def _resolve(self, name: str) -> Optional[Tuple[Any, str]]:
        if name in self._clients:
            return self._clients[name]
        spec = next((p for p in PROVIDER_CATALOG if p.name == name), None)
        if not spec:
            return None
        api_key = self._env.get(spec.env_key, "").strip()
        client = get_llm_client(name, api_key, spec.base_url)
        if not client:
            return None
        self._clients[name] = (client, spec.default_model)
        return self._clients[name]

    async def complete(self, messages: List[Dict[str, str]], max_tokens: int = 1024) -> LLMRouterResult:
        last_err: Optional[Exception] = None
        for idx, name in enumerate(self.providers):
            resolved = self._resolve(name)
            if not resolved:
                continue
            client, model = resolved
            try:
                if name == "anthropic":
                    system = next((m["content"] for m in messages if m["role"] == "system"), "")
                    user_msgs = [m for m in messages if m["role"] != "system"]
                    resp = await client.messages.create(
                        model=model, system=system, messages=user_msgs,
                        max_tokens=max_tokens,
                    )
                    text = resp.content[0].text
                elif name == "gemini":
                    text = await client.chat(messages)
                else:
                    resp = await client.chat.completions.create(
                        model=model, messages=messages,
                        max_tokens=max_tokens, temperature=0.7,
                    )
                    text = resp.choices[0].message.content or ""
                return LLMRouterResult(
                    text=text, provider=name, model=model,
                    used_fallback=(idx > 0),
                )
            except Exception as e:
                last_err = e
                logger.warning(f"LLM provider '{name}' failed: {e}")
                continue
        raise RuntimeError(f"All LLM providers failed. Last error: {last_err}")


# ---------------------------------------------------------------------------
# Convenience: build router from env
# ---------------------------------------------------------------------------
def build_default_router() -> AsyncLLMRouter:
    """
    LLM_FAILOVER_LIST env var: comma-separated priority.
    Default: anthropic,openai,gemini,groq,deepseek,openrouter,mistral,ollama
    Only providers with a key (or ollama if reachable) will be tried.
    """
    raw = os.getenv("LLM_FAILOVER_LIST", "").strip()
    if raw:
        order = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        order = [p.name for p in PROVIDER_CATALOG]
    return AsyncLLMRouter(order)
