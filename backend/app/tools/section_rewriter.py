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
保持原意，优先增强动作、技术细节、量化表达和与目标岗位的相关性。
这是原简历中的单个文字槽位，不得输出整份简历、标题、Markdown、项目符号或额外段落。"""


_SECTION_GUIDANCE = {
    "work_experience": """工作经历专用要求：
- 使用 STAR 思路组织已有事实：动作、职责范围、采用的方法或技术、已有结果。
- 优先使用明确的动作动词，删除“负责相关工作”等空泛表达。
- 保留原公司、职位、时间、业务范围和技术事实；原文没有的数据或业绩数字绝不补写。
- 输出一段可直接替换原文的职业化描述，不添加公司名、职位名或日期标题。""",
    "project_experience": """项目经历专用要求：
- 突出项目目标、本人动作、技术方案、架构或技术决策，以及原文已有的工程结果。
- 保留所有明确技术名词、参数、规模和业务事实，提升因果关系与技术表达的准确性。
- 结合 JD 调整信息顺序，但不得把未使用的岗位技术写进项目。
- 输出一段可直接替换当前项目描述的正文，不重复项目名称和小标题。""",
    "self_evaluation": """个人优势/自我评价专用要求：
- 删除“认真负责、学习能力强”等没有证据支撑的空泛套话。
- 只保留原文可验证的能力、工具使用方式、协作方式或问题解决特点。
- 用简洁、克制、职业化的第一人称省略表达，不虚构经验年限或能力等级。
- 输出一个紧凑段落，不添加“自我评价”标题。""",
    "skills": """技能专用要求：
- 规范技能名称、去重并按目标岗位相关性排序。
- 只保留 original_content 或 evidence_context 中明确出现的技术；JD 仅用于排序，不能证明候选人具备该技能。
- 不添加熟练度、工作年限或能力等级，除非原文明确写出。
- 只输出使用中文顿号分隔的技能列表，不添加解释、分类标题或句号。""",
}


def build_section_rewrite_prompt(request: SectionRewriteRequest) -> str:
    """Build a self-contained prompt for one independently rewritable section."""
    payload = request.model_dump()
    guidance = _SECTION_GUIDANCE[request.section_type]
    if request.original_content:
        original_length = len(request.original_content)
        maximum_length = original_length + max(2, min(8, original_length // 12))
        layout_guidance = (
            f"为避免破坏原简历排版，rewritten_content 最多 {maximum_length} 个字符，"
            "保持单段且不换行；优先在原文长度内重组表达，不要为了显得丰富而扩写。"
        )
    else:
        layout_guidance = "原文为空时只生成紧凑的技能列表，保持单段且不换行。"
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
5. 当 skills 的 original_content 为空时，只能从 evidence_context 中提取明确出现的技能；
   evidence_context 没有出现的技能不得添加，JD 关键词不能作为事实依据。
6. evidence_context 仅用于核实事实，不得整段复制到 rewritten_content。
7. {layout_guidance}

{guidance}

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
