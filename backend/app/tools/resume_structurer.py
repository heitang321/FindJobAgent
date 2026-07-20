"""Tool 1.4：结构化并评估已提取的简历文本。

本模块是简历结构化的公开边界。提示词构建、确定性解析、结果规范化和已配置模型适配器
都放在私有实现模块中，使调用方只需要使用一个小而清晰的接口。
"""

from __future__ import annotations

from inspect import isawaitable
from typing import Any

from app.tools._resume_structurer.fallback import fallback_structure
from app.tools._resume_structurer.llm import (
    LLMCallable,
    build_resume_structure_prompt,
    configured_llm,
    parse_llm_response,
)
from app.tools._resume_structurer.result import normalize_result

__all__ = ["LLMCallable", "build_resume_structure_prompt", "resume_structurer"]


async def resume_structurer(
    raw_text: str,
    llm: LLMCallable | None = None,
    use_configured_llm: bool = False,
) -> dict[str, Any]:
    """返回规范化后的结构化简历和评估结果。

    如果传入 ``llm``，则优先使用它。否则只有当 ``use_configured_llm`` 为 true 时
    才使用已配置模型。模型不可用、响应无效或模型报错时，会回退到确定性解析，
    同时将错误保存在 ``evaluation.llm_error`` 中。

    配置模型使用原生异步调用；测试和扩展代码也可以注入同步 callable，
    本函数会自动识别返回值是否可等待。
    """
    model = llm
    if model is None and use_configured_llm:
        model = configured_llm

    if model is None:
        return normalize_result(fallback_structure(raw_text))

    try:
        response = model(build_resume_structure_prompt(raw_text))
        if isawaitable(response):
            response = await response
        result = normalize_result(parse_llm_response(response))
        result["evaluation"]["analysis_source"] = (
            result["evaluation"]["analysis_source"] or "llm"
        )
        return result
    except Exception as exc:
        result = normalize_result(fallback_structure(raw_text))
        result["evaluation"]["llm_error"] = str(exc)
        return result
