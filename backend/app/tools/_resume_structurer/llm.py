"""LLM prompt, response parsing, and configured-model adapter."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any


LLMCallable = Callable[[str], str | dict[str, Any]]


def build_resume_structure_prompt(raw_text: str) -> str:
    """Build the strict-JSON prompt used for resume analysis."""
    return f"""
你是简历分析 Agent。请只输出 JSON，不要输出 markdown 代码块。
按以下 schema 结构化简历并给出深度评估：
{{
  "structured_resume": {{
    "basic_info": {{"name": "", "phone": "", "email": "", "location": ""}},
    "education": [{{"school": "", "major": "", "degree": "", "period": ""}}],
    "work_experience": [{{"company": "", "position": "", "period": "", "description": ""}}],
    "project_experience": [{{"name": "", "role": "", "description": ""}}],
    "skills": ["", ""],
    "self_evaluation": ""
  }},
  "evaluation": {{
    "analysis_source": "llm",
    "completeness_score": 0,
    "overall_summary": "不少于120字，整体评价候选人的定位、竞争力、简历最大问题和建议方向",
    "strengths": ["每条不少于30字，说明具体证据，不要泛泛而谈"],
    "weaknesses": ["每条不少于30字，说明具体证据和影响"],
    "missing_sections": [""],
    "section_reviews": [
      {{"section": "基本信息/教育经历/工作经历/项目经历/技能/自我评价", "score": 0, "comment": "不少于50字的分模块评价"}}
    ],
    "improvement_suggestions": [
      {{"priority": "high|medium|low", "section": "", "problem": "", "suggestion": "", "example": ""}}
    ],
    "keyword_analysis": {{
      "detected_keywords": [""],
      "missing_keywords": [""],
      "keyword_density_comment": ""
    }},
    "ats_readability": "从 ATS/HR 快速浏览角度分析可读性，不少于80字",
    "risk_points": ["潜在扣分点、表达风险或信息矛盾"],
    "rewrite_examples": [
      {{"before": "原简历表达", "after": "建议改写", "reason": "为什么这样改"}}
    ],
    "llm_error": ""
  }}
}}

要求：
1. 必须尽可能从原文抽取真实信息，不要编造不存在的学校、公司、时间。
2. 如果没有工作经历，不要凭空生成工作经历，但要在 weakness 和 missing_sections 说明。
3. 项目经历需要保留项目名称、角色、技术栈和关键成果。
4. skills 不要只给关键词，也可以保留较完整技能描述。
5. evaluation 必须是详细分析，不要只输出一小段话。

简历原文：
{raw_text}
""".strip()


def parse_llm_response(response: str | dict[str, Any]) -> dict[str, Any]:
    """Parse a dictionary or a JSON response, including fenced JSON."""
    if isinstance(response, dict):
        return response

    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def configured_llm(prompt: str) -> str:
    """Call the configured OpenAI-compatible model."""
    from app.model.openai_compatible import chat_completion

    return chat_completion(
        prompt,
        system_prompt=(
            "你是资深招聘顾问和简历优化专家。你必须输出严格 JSON，"
            "并给出详细、具体、可执行的中文简历分析。"
        ),
    )
