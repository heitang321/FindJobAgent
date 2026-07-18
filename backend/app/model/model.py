"""LLM 模型封装（单例）。

通过 app.core.config.settings 统一读取 AI_API_KEY、AI_BASE_URL、
AI_MODEL 等配置，和队友的 openai_compatible.py 使用同一套配置源。
"""
from langchain_openai import ChatOpenAI

from app.core.config import settings


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
            )
        return MyModel._model


if __name__ == "__main__":
    model = MyModel.get_model()
    rs = model.invoke("你好")
    print(rs.content)
