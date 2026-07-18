"""Shared OpenAI-compatible chat client used by application tools."""
from __future__ import annotations

import httpx

from app.core.config import settings


def is_llm_configured() -> bool:
    """Return True when an OpenAI-compatible model is configured."""
    return bool(settings.AI_API_KEY and settings.AI_BASE_URL and settings.AI_MODEL)


def chat_completion(prompt: str, system_prompt: str = "") -> str:
    """Call an OpenAI-compatible Chat Completions endpoint.

    The endpoint is intentionally small and dependency-light: it uses httpx
    instead of the OpenAI SDK so DeepSeek/OpenRouter/MiMo/custom providers can
    share the same code path.
    """
    if not is_llm_configured():
        raise RuntimeError("AI model is not configured. Set AI_API_KEY, AI_BASE_URL and AI_MODEL.")

    base_url = settings.AI_BASE_URL.rstrip("/")
    url = f"{base_url}/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=settings.AI_TIMEOUT_SECONDS) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.AI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.AI_MODEL,
                "messages": messages,
                "temperature": settings.AI_TEMPERATURE,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]
