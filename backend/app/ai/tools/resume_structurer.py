"""Tool 1.4: 简历结构化提取 + 评估。

这是 Agent 1 内部唯一调用 LLM 的步骤。输入原始文本，让 LLM 按预定义
schema 输出结构化简历和评估报告。

LLM 调用通过注入的 callable 实现，生产环境可接入 OpenAI 兼容客户端，
测试环境可传入 fake LLM。如果未提供 LLM callable，则使用确定性 fallback
保持本地开发可用。
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

# LLM callable 类型：接收 prompt 字符串，返回 JSON 字符串或 dict
LLMCallable = Callable[[str], str | dict[str, Any]]


# 空的结构化简历模板
EMPTY_STRUCTURED_RESUME: dict[str, Any] = {
    "basic_info": {"name": "", "phone": "", "email": "", "location": ""},
    "education": [],
    "work_experience": [],
    "project_experience": [],
    "skills": [],
    "self_evaluation": "",
}


def _empty_result() -> dict[str, Any]:
    """返回空的结果模板（深拷贝避免共享引用）。"""
    return {
        "structured_resume": json.loads(json.dumps(EMPTY_STRUCTURED_RESUME, ensure_ascii=False)),
        "evaluation": {
            "analysis_source": "fallback",
            "completeness_score": 0,
            "overall_summary": "",
            "strengths": [],
            "weaknesses": [],
            "missing_sections": [],
            "section_reviews": [],
            "improvement_suggestions": [],
            "keyword_analysis": {
                "detected_keywords": [],
                "missing_keywords": [],
                "keyword_density_comment": "",
            },
            "ats_readability": "",
            "risk_points": [],
            "rewrite_examples": [],
            "llm_error": "",
        },
    }


# 简历各部分的中文映射，用于 fallback 的缺失检测
_SECTION_NAMES: dict[str, str] = {
    "basic_info": "基本信息",
    "education": "教育经历",
    "work_experience": "工作经历",
    "project_experience": "项目经历",
    "skills": "技能清单",
    "self_evaluation": "自我评价",
}


def build_resume_structure_prompt(raw_text: str) -> str:
    """构建让 LLM 输出结构化简历 JSON 的 prompt。

    要求 LLM 只输出 JSON，不输出 markdown 代码块。
    """
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


def _parse_llm_response(response: str | dict[str, Any]) -> dict[str, Any]:
    """解析 LLM 的响应，支持 dict 直接返回或 JSON 字符串。

    自动剥离 markdown 代码块包裹（```json ... ```）。
    """
    if isinstance(response, dict):
        return response

    text = response.strip()
    # 剥离 markdown 代码块
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _first_match(pattern: str, text: str) -> str:
    """正则匹配第一个结果，无匹配返回空字符串。"""
    match = re.search(pattern, text, re.I)
    return match.group(1).strip() if match else ""


def _lines(raw_text: str) -> list[str]:
    """Return non-empty normalized lines."""
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def _extract_between_sections(raw_text: str, start_heading: str, stop_headings: list[str]) -> str:
    """Extract text after a heading until the next known heading."""
    pattern = rf"{re.escape(start_heading)}\s*(.*)"
    match = re.search(pattern, raw_text, re.S)
    if not match:
        return ""
    tail = match.group(1)
    stop_positions = [
        pos
        for heading in stop_headings
        if (pos := tail.find(heading)) >= 0
    ]
    if stop_positions:
        tail = tail[: min(stop_positions)]
    return tail.strip()


def _extract_name(raw_text: str) -> str:
    """Extract Chinese name from explicit label or repeated header line."""
    name = _first_match(r"(?:姓名[:：]\s*)([^\s|,，；;]{2,12})", raw_text)
    if name:
        return name

    section_headings = {"个人优势", "教育经历", "项目经历", "资格证书", "专业技能", "工作经历"}
    for line in _lines(raw_text):
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) >= 2 and parts[0] == parts[1] and re.fullmatch(r"[\u4e00-\u9fff]{2,4}", parts[0]):
            return parts[0]
        if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", line) and line not in section_headings:
            return line
    return ""


def _extract_location(raw_text: str) -> str:
    return (
        _first_match(r"(?:所在地|现居|所在城市|城市)[:：]\s*([\u4e00-\u9fff]{2,10})", raw_text)
        or _first_match(r"期望城市[:：]\s*([\u4e00-\u9fff]{2,10})", raw_text)
    )


def _extract_education(raw_text: str) -> list[dict[str, str]]:
    education: list[dict[str, str]] = []
    degree_pattern = r"(博士|硕士|本科|大专|高中|中专)"
    period_pattern = r"(\d{4}(?:[./-]\d{1,2})?\s*[-至~—]\s*(?:\d{4}(?:[./-]\d{1,2})?|至今))"

    for line in _lines(raw_text):
        if not re.search(r"大学|学院|学校", line):
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) >= 3:
            school = next((part for part in parts if re.search(r"大学|学院|学校", part)), "")
            degree = next((part for part in parts if re.fullmatch(degree_pattern, part)), "")
            period = next((part for part in parts if re.search(period_pattern, part)), "")
            major = next(
                (
                    part
                    for part in parts
                    if part not in {school, degree, period}
                    and not re.search(r"排名|课程|成绩|证书|蓝桥杯|挑战赛", part)
                ),
                "",
            )
            if school or degree or major or period:
                education.append(
                    {"school": school, "major": major, "degree": degree, "period": period}
                )
                break

    if not education and re.search(r"教育|本科|硕士|博士|大专|大学|学院", raw_text):
        education.append({"school": "", "major": "", "degree": "", "period": ""})
    return education


def _extract_project_experience(raw_text: str) -> list[dict[str, str]]:
    projects: list[dict[str, str]] = []
    period_pattern = r"\d{4}(?:[./-]\d{1,2})?\s*[-至~—]\s*(?:\d{4}(?:[./-]\d{1,2})?|至今)"
    stop_headings = ["资格证书", "专业技能", "教育经历", "工作经历", "个人优势"]
    section_text = _extract_between_sections(raw_text, "项目经历", stop_headings)

    for line in _lines(raw_text):
        if "|" not in line or not re.search(period_pattern, line):
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) >= 2:
            name = parts[0]
            role = parts[1] if len(parts) > 1 else ""
            if re.search(r"大学|学院", name):
                continue
            projects.append(
                {
                    "name": name,
                    "role": role,
                    "description": section_text[:800] if section_text else "",
                }
            )
            break

    if not projects and section_text:
        first_line = _lines(section_text)[0] if _lines(section_text) else ""
        projects.append({"name": first_line, "role": "", "description": section_text[:800]})
    elif not projects and re.search(r"项目经历|项目经验|项目", raw_text):
        projects.append({"name": "", "role": "", "description": ""})
    return projects


def _extract_skills(raw_text: str) -> list[str]:
    skill_line = _first_match(r"(?:技能|专业技能|技术栈)[:：]\s*([^\n]+)", raw_text)
    if skill_line:
        return [item.strip() for item in re.split(r"[,，、/| ]+", skill_line) if item.strip()]

    skill_section = _extract_between_sections(
        raw_text,
        "专业技能",
        ["工作经历", "项目经历", "教育经历", "资格证书", "个人优势", "程智涵 |"],
    )
    if not skill_section:
        return []

    numbered_items = re.findall(
        r"(?:^|\n)\s*\d+[.、]\s*(.*?)(?=(?:\n\s*\d+[.、]\s*)|\Z)",
        skill_section,
        flags=re.S,
    )
    if numbered_items:
        return [" ".join(item.split()) for item in numbered_items if item.strip()]

    known_skills = [
        "Python",
        "LangChain",
        "ReAct",
        "RAG",
        "FastAPI",
        "WebSocket",
        "Docker Compose",
        "Docker",
        "SQLite",
        "MySQL",
        "DeepSeek",
        "GLM",
        "OpenAI",
        "TTS",
        "Java",
        "C/C++",
    ]
    return [skill for skill in known_skills if re.search(re.escape(skill), skill_section, re.I)]


def _extract_self_evaluation(raw_text: str) -> str:
    return _extract_between_sections(raw_text, "个人优势", ["教育经历", "项目经历", "工作经历", "专业技能"])[:500]


def _fallback_structure(raw_text: str) -> dict[str, Any]:
    """无 LLM 时的确定性 fallback 结构化。

    使用正则表达式提取基本信息（姓名、电话、邮箱、技能），
    检测简历各部分是否存在，计算完整度评分。
    """
    result = _empty_result()
    resume = result["structured_resume"]
    evaluation = result["evaluation"]

    resume["basic_info"]["phone"] = _first_match(r"(1[3-9]\d{9})", raw_text)
    resume["basic_info"]["email"] = _first_match(
        r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", raw_text
    )
    name = _extract_name(raw_text)
    resume["basic_info"]["name"] = name
    resume["basic_info"]["location"] = _extract_location(raw_text)

    resume["education"] = _extract_education(raw_text)
    resume["project_experience"] = _extract_project_experience(raw_text)
    resume["skills"] = _extract_skills(raw_text)
    resume["self_evaluation"] = _extract_self_evaluation(raw_text)

    if re.search(r"工作经历|工作经验|任职|公司", raw_text):
        resume["work_experience"].append(
            {"company": "", "position": "", "period": "", "description": ""}
        )

    sections_present = {
        "basic_info": bool(resume["basic_info"]["phone"] or resume["basic_info"]["email"] or name),
        "education": bool(resume["education"]),
        "work_experience": bool(resume["work_experience"]),
        "project_experience": bool(resume["project_experience"]),
        "skills": bool(resume["skills"]),
    }
    score = int(sum(1 for present in sections_present.values() if present) / len(sections_present) * 100)

    missing = [
        _SECTION_NAMES[key] for key, present in sections_present.items() if not present
    ]

    evaluation["completeness_score"] = score
    evaluation["analysis_source"] = "fallback"
    evaluation["overall_summary"] = (
        "当前未配置可用 AI 模型，系统使用确定性规则完成基础结构化。"
        "该结果可用于本地调试，但深度评价、表达改写和岗位导向建议需要配置 AI_API_KEY、AI_BASE_URL 和 AI_MODEL 后生成。"
    )
    strengths = []
    if sections_present["basic_info"]:
        strengths.append("基本联系方式清晰")
    if sections_present["project_experience"]:
        strengths.append("包含项目经历")
    if sections_present["skills"]:
        strengths.append("包含技能描述")
    evaluation["strengths"] = strengths
    evaluation["weaknesses"] = [f"缺少{item}" for item in missing] if missing else []
    evaluation["missing_sections"] = missing
    evaluation["section_reviews"] = [
        {
            "section": "基本信息",
            "score": 80 if sections_present["basic_info"] else 20,
            "comment": "规则检测到手机号、邮箱或姓名等基础信息。" if sections_present["basic_info"] else "未检测到完整基础信息。",
        },
        {
            "section": "项目经历",
            "score": 80 if sections_present["project_experience"] else 20,
            "comment": "规则检测到项目经历，可继续用 AI 分析项目表达质量。" if sections_present["project_experience"] else "未检测到项目经历。",
        },
    ]
    evaluation["improvement_suggestions"] = [
        {
            "priority": "high",
            "section": item,
            "problem": f"{item}缺失或不够清晰",
            "suggestion": "补充该模块的关键信息，并使用量化结果增强可信度。",
            "example": "",
        }
        for item in missing
    ]
    evaluation["keyword_analysis"] = {
        "detected_keywords": resume["skills"],
        "missing_keywords": [],
        "keyword_density_comment": "规则模式只能识别显式技能，配置 AI 后可获得更完整的关键词覆盖分析。",
    }
    evaluation["ats_readability"] = "规则模式未进行完整 ATS 可读性判断。建议配置 AI 后分析版式层级、关键词覆盖、项目成果表达和 HR 快速浏览友好度。"
    evaluation["risk_points"] = ["未启用 AI 深度分析，当前仅为基础结构化结果。"]
    evaluation["rewrite_examples"] = []
    return result


def _normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    """规范化 LLM 输出，确保字段类型和结构符合 schema。"""
    result = _empty_result()
    structured = data.get("structured_resume") or {}
    evaluation = data.get("evaluation") or {}

    # 规范化 basic_info
    basic_info = structured.get("basic_info") or {}
    for key in ("name", "phone", "email", "location"):
        result["structured_resume"]["basic_info"][key] = str(basic_info.get(key) or "")

    # 规范化列表字段
    for key in ("education", "work_experience", "project_experience", "skills"):
        value = structured.get(key)
        result["structured_resume"][key] = value if isinstance(value, list) else []

    result["structured_resume"]["self_evaluation"] = str(structured.get("self_evaluation") or "")

    # 规范化评分
    result["evaluation"]["analysis_source"] = str(evaluation.get("analysis_source") or "")
    result["evaluation"]["overall_summary"] = str(evaluation.get("overall_summary") or "")
    result["evaluation"]["ats_readability"] = str(evaluation.get("ats_readability") or "")
    result["evaluation"]["llm_error"] = str(evaluation.get("llm_error") or "")

    score = evaluation.get("completeness_score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    result["evaluation"]["completeness_score"] = max(0, min(100, score))

    # 规范化列表字段
    for key in (
        "strengths",
        "weaknesses",
        "missing_sections",
        "section_reviews",
        "improvement_suggestions",
        "risk_points",
        "rewrite_examples",
    ):
        value = evaluation.get(key)
        result["evaluation"][key] = value if isinstance(value, list) else []

    keyword_analysis = evaluation.get("keyword_analysis")
    if isinstance(keyword_analysis, dict):
        result["evaluation"]["keyword_analysis"] = {
            "detected_keywords": keyword_analysis.get("detected_keywords")
            if isinstance(keyword_analysis.get("detected_keywords"), list)
            else [],
            "missing_keywords": keyword_analysis.get("missing_keywords")
            if isinstance(keyword_analysis.get("missing_keywords"), list)
            else [],
            "keyword_density_comment": str(keyword_analysis.get("keyword_density_comment") or ""),
        }

    return result


def _configured_llm(prompt: str) -> str:
    """Call configured model lazily to keep tests and fallback dependency-light."""
    from app.ai.model.openai_compatible import chat_completion

    return chat_completion(
        prompt,
        system_prompt=(
            "你是资深招聘顾问和简历优化专家。你必须输出严格 JSON，"
            "并给出详细、具体、可执行的中文简历分析。"
        ),
    )


def resume_structurer(
    raw_text: str,
    llm: LLMCallable | None = None,
    use_configured_llm: bool = False,
) -> dict[str, Any]:
    """Return a normalized structured resume and evaluation.

    An injected ``llm`` is used when supplied. Otherwise the configured model
    is used only when ``use_configured_llm`` is true. Any unavailable model,
    invalid response, or model error falls back to deterministic parsing while
    preserving the error in ``evaluation.llm_error``.
    """
    model = llm
    if model is None and use_configured_llm:
        model = configured_llm

    if model is None:
        return normalize_result(fallback_structure(raw_text))

    try:
        response = model(build_resume_structure_prompt(raw_text))
        result = normalize_result(parse_llm_response(response))
        result["evaluation"]["analysis_source"] = (
            result["evaluation"]["analysis_source"] or "llm"
        )
        return result
    except Exception as exc:
        result = normalize_result(fallback_structure(raw_text))
        result["evaluation"]["llm_error"] = str(exc)
        return result
