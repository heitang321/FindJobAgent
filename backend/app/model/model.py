"""LLM 模型封装（单例）。

通过 app.core.config.settings 统一读取 AI_API_KEY、AI_BASE_URL、
AI_MODEL 等配置，和队友的 openai_compatible.py 使用同一套配置源。
"""
import ssl

import httpx
from langchain_openai import ChatOpenAI

from app.core.config import settings

# 自定义 SSL 上下文，解决 DashScope 等云服务的 EOF 问题
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.set_ciphers("DEFAULT")

# 带重试和自定义 SSL 的 httpx 客户端
_http_client = httpx.Client(
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
    transport=httpx.HTTPTransport(retries=2),
)


class MyModel:
    _model = None

    @staticmethod
    def get_model():
        if MyModel._model is None:
            MyModel._model = ChatOpenAI(
                model=settings.AI_MODEL,
                api_key=settings.AI_API_KEY,
                base_url=settings.AI_BASE_URL,
                streaming=True,
                temperature=settings.AI_TEMPERATURE,
                http_client=_http_client,
            )
        return MyModel._model


if __name__ == "__main__":
    model = MyModel.get_model()
    rs = model.invoke("你好")
    print(rs.content)
