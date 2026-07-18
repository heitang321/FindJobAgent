"""Tool 3.1: rewrite one resume section with grounded LLM output."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.schemas.optimization import SectionRewriteRequest, SectionRewriteResult


RewriteLLM = Callable[[str], str | dict[str, Any]]


_SYSTEM_PROMPT = """你是资深简历优化专家。只输出严格 JSON。
你只能改写输入段落中已有的真实经历，不得虚构公司、项目、技能、数字、职责或成果。
岗位关键词只能在原文已有事实能够支持时自然融入；无法验证的关键词不得添加。
保持原意，优先增强动作、技术细节、量化表达和与目标岗位的相关性。"""


def build_section_rewrite_prompt(request: SectionRewriteRequest) -> str:
    """Build a self-contained prompt for one independently rewritable section."""
    payload = request.model_dump()
    return f"""请优化以下单个简历段落，并按 schema 返回 JSON：
{{
  "section_type": "{request.section_type}",
  "original_content": "必须原样返回输入内容",
  "rewritten_content": "优化后的段落",
  "change_reason": "修改原因",
  "changes": [{{"type": "added|modified|removed", "description": "具体修改"}}]
}}

约束：
1. 不得编造输入中不存在的经历或能力。
2. 没有可靠依据时保持原文，不要为了匹配 JD 强行添加关键词。
3. skills 段落返回逗号分隔的技能列表；其他段落返回可直接放入简历的正文。
4. original_content 必须与输入完全一致。

输入：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def _parse_response(response: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _configured_llm(prompt: str) -> str:
    from app.model.openai_compatible import chat_completion

    return chat_completion(prompt, system_prompt=_SYSTEM_PROMPT)


def _unchanged_result(request: SectionRewriteRequest) -> SectionRewriteResult:
    return SectionRewriteResult(
        section_type=request.section_type,
        original_content=request.original_content,
        rewritten_content=request.original_content,
        change_reason="未启用 AI 重写，保留原始内容。",
        changes=[],
    )


def section_rewriter(
    request: SectionRewriteRequest,
    llm: RewriteLLM | None = None,
    use_configured_llm: bool = True,
) -> SectionRewriteResult:
    """Rewrite one section and validate the structured result.

    ``llm`` is the true external seam: tests inject an in-memory adapter while
    production uses the configured OpenAI-compatible adapter.
    """
    model = llm
    if model is None and use_configured_llm:
        model = _configured_llm
    if model is None:
        return _unchanged_result(request)

    data = _parse_response(model(build_section_rewrite_prompt(request)))
    data["section_type"] = request.section_type
    data["original_content"] = request.original_content
    result = SectionRewriteResult.model_validate(data)
    if not result.rewritten_content.strip():
        return _unchanged_result(request)
    return result
