"""应用工具共用的 OpenAI 兼容聊天客户端。"""
from __future__ import annotations

import httpx

from app.core.config import settings


def is_llm_configured() -> bool:
    """当已配置 OpenAI 兼容模型时返回 True。"""
    return bool(settings.AI_API_KEY and settings.AI_BASE_URL and settings.AI_MODEL)


def chat_completion(prompt: str, system_prompt: str = "") -> str:
    """调用 OpenAI 兼容的聊天补全接口。

    这里刻意保持实现简短、依赖较少：使用 httpx 而不是 OpenAI SDK，
    这样 DeepSeek、OpenRouter、MiMo 或自定义服务商可以共用同一条代码路径。
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
