"""应用工具共用的 OpenAI 兼容聊天客户端。"""
from __future__ import annotations

import ssl
import time

import httpx

from app.core.config import settings

# 重试配置
_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 5, 10]  # 秒，逐次递增

# SSL 上下文：禁用不安全的 renegotiation 检查，
# 解决部分云服务商（如阿里云 DashScope）的 EOF 问题
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
        http2=False,  # 部分服务端不支持 HTTP/2，关闭避免握手问题
        limits=httpx.Limits(
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=60.0,
        ),
    )


def chat_completion(prompt: str, system_prompt: str = "") -> str:
    """调用 OpenAI 兼容的聊天补全接口。

    包含自动重试机制：遇到 SSL EOF、连接重置等网络错误时
    会退避后重试最多 3 次。
    """
    if not is_llm_configured():
        raise RuntimeError("AI model is not configured. Set AI_API_KEY, AI_BASE_URL and AI_MODEL.")

    base_url = settings.AI_BASE_URL.rstrip("/")
    url = f"{base_url}/chat/completions"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": settings.AI_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }
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

    # 所有重试都失败，抛出最后一个错误
    raise last_error  # type: ignore[misc]
