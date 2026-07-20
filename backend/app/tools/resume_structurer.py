"""Tool 1.4: structure and evaluate extracted resume text.

This module is the public seam for resume structuring. Prompt construction,
deterministic parsing, result normalization, and the configured-model adapter
live in private implementation modules so callers only need one small interface.
"""

from __future__ import annotations

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
    """Return a normalized structured resume and evaluation.

    An injected ``llm`` is used when supplied. Otherwise the configured model
    is used only when ``use_configured_llm`` is true. Any unavailable model,
    invalid response, or model error falls back to deterministic parsing while
    preserving the error in ``evaluation.llm_error``.

    重构后是 async：因为 configured_llm 改成 `await MyModel.get_model().ainvoke()`，
    注入的 LLMCallable 也是 async callable（见 _resume_structurer/llm.py）。
    """
    model = llm
    if model is None and use_configured_llm:
        model = configured_llm

    if model is None:
        return normalize_result(fallback_structure(raw_text))

    try:
        response = await model(build_resume_structure_prompt(raw_text))
        result = normalize_result(parse_llm_response(response))
        result["evaluation"]["analysis_source"] = (
            result["evaluation"]["analysis_source"] or "llm"
        )
        return result
    except Exception as exc:
        result = normalize_result(fallback_structure(raw_text))
        result["evaluation"]["llm_error"] = str(exc)
        return result
