"""应用工具共用的 OpenAI 兼容聊天客户端。

支持两种调用模式：
- chat_completion(): 同步一次性返回（带重试）
- chat_completion_stream(): 流式逐 token 返回（SSE 透传）

均支持 history 参数，用于传递多轮对话历史。
"""
from __future__ import annotations

import json
import ssl
import time
from collections.abc import Generator
from typing import Any

import httpx

from app.core.config import settings

# 重试配置
_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 5, 10]  # 秒，逐次递增

# SSL 上下文：解决阿里云 DashScope 的 EOF 问题
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.set_ciphers("DEFAULT")


def is_llm_configured() -> bool:
    """当已配置 OpenAI 兼容模型时返回 True。"""
    return bool(settings.AI_API_KEY and settings.AI_BASE_URL and settings.AI_MODEL)


def _create_client() -> httpx.Client:
    """创建带自定义 SSL 上下文和连接池的 httpx 客户端。"""
    return httpx.Client(
        timeout=httpx.Timeout(
            timeout=settings.AI_TIMEOUT_SECONDS,
            connect=30.0,
            read=settings.AI_TIMEOUT_SECONDS,
            write=30.0,
        ),
        verify=_ssl_ctx,
        http2=False,
        limits=httpx.Limits(
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=60.0,
        ),
    )


def _build_messages(
    prompt: str,
    system_prompt: str = "",
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """构建 LLM messages 数组（system + history + 当前 prompt）。"""
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    return messages


def chat_completion(
    prompt: str,
    system_prompt: str = "",
    *,
    json_mode: bool = True,
    history: list[dict[str, str]] | None = None,
) -> str:
    """调用 OpenAI 兼容的聊天补全接口（一次性返回，带重试）。

    Args:
        prompt: 用户问题
        system_prompt: 系统提示词
        json_mode: True 时强制返回 JSON（结构化提取用）。
                   False 时返回自然语言（问答、数据分析用）。
        history: 多轮对话历史，格式 [{"role": "user"|"assistant", "content": "..."}]
    """
    if not is_llm_configured():
        raise RuntimeError("AI model is not configured. Set AI_API_KEY, AI_BASE_URL and AI_MODEL.")

    base_url = settings.AI_BASE_URL.rstrip("/")
    url = f"{base_url}/chat/completions"
    messages = _build_messages(prompt, system_prompt, history)

    payload: dict[str, Any] = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": settings.AI_TEMPERATURE,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {settings.AI_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            with _create_client() as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
            return data["choices"][0]["message"]["content"]
        except (
            httpx.TransportError,
            httpx.RemoteProtocolError,
            ssl.SSLError,
            ConnectionError,
        ) as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF[attempt]
                print(f"  [LLM 重试] 第 {attempt + 1} 次失败: {e}，{wait}s 后重试...")
                time.sleep(wait)
            else:
                print(f"  [LLM 重试] 已达最大重试次数 {_MAX_RETRIES}，放弃: {e}")

    raise last_error  # type: ignore[misc]


def chat_completion_stream(
    prompt: str,
    system_prompt: str = "",
    history: list[dict[str, str]] | None = None,
) -> Generator[str, None, None]:
    """流式调用 OpenAI 兼容的聊天补全接口，逐 token yield。

    使用 SSE stream 模式，DashScope/OpenAI 均支持。
    不带重试机制（流式无法中途重试）。

    Args:
        prompt: 用户问题
        system_prompt: 系统提示词
        history: 多轮对话历史

    Yields:
        每个 token 片段 (str)
    """
    if not is_llm_configured():
        raise RuntimeError("AI model is not configured. Set AI_API_KEY, AI_BASE_URL and AI_MODEL.")

    base_url = settings.AI_BASE_URL.rstrip("/")
    url = f"{base_url}/chat/completions"
    messages = _build_messages(prompt, system_prompt, history)

    payload: dict[str, Any] = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": settings.AI_TEMPERATURE,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {settings.AI_API_KEY}",
        "Content-Type": "application/json",
    }

    with _create_client() as client:
        with client.stream("POST", url, headers=headers, json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue
