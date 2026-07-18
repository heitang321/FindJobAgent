"""Deterministic resume parsing used when no LLM result is available."""

from __future__ import annotations

import re
from typing import Any

from app.tools._resume_structurer.result import empty_result


SECTION_NAMES: dict[str, str] = {
    "basic_info": "基本信息",
    "education": "教育经历",
    "work_experience": "工作经历",
    "project_experience": "项目经历",
    "skills": "技能清单",
}


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I)
    return match.group(1).strip() if match else ""


def _lines(raw_text: str) -> list[str]:
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def _extract_between_sections(
    raw_text: str, start_heading: str, stop_headings: list[str]
) -> str:
    pattern = rf"{re.escape(start_heading)}\s*(.*)"
    match = re.search(pattern, raw_text, re.S)
    if not match:
        return ""

    tail = match.group(1)
    stop_positions = [
        pos for heading in stop_headings if (pos := tail.find(heading)) >= 0
    ]
    if stop_positions:
        tail = tail[: min(stop_positions)]
    return tail.strip()


def _extract_name(raw_text: str) -> str:
    name = _first_match(r"(?:姓名[:：]\s*)([^\s|,，；;]{2,12})", raw_text)
    if name:
        return name

    section_headings = {
        "个人优势",
        "教育经历",
        "项目经历",
        "资格证书",
        "专业技能",
        "工作经历",
    }
    for line in _lines(raw_text):
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if (
            len(parts) >= 2
            and parts[0] == parts[1]
            and re.fullmatch(r"[\u4e00-\u9fff]{2,4}", parts[0])
        ):
            return parts[0]
        if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", line) and line not in section_headings:
            return line
    return ""


def _extract_location(raw_text: str) -> str:
    return _first_match(
        r"(?:所在地|现居|所在城市|城市)[:：]\s*([\u4e00-\u9fff]{2,10})",
        raw_text,
    ) or _first_match(r"期望城市[:：]\s*([\u4e00-\u9fff]{2,10})", raw_text)


def _extract_education(raw_text: str) -> list[dict[str, str]]:
    education: list[dict[str, str]] = []
    degree_pattern = r"(博士|硕士|本科|大专|高中|中专)"
    period_pattern = (
        r"(\d{4}(?:[./-]\d{1,2})?\s*[-至~—]\s*(?:\d{4}(?:[./-]\d{1,2})?|至今))"
    )

    for line in _lines(raw_text):
        if not re.search(r"大学|学院|学校", line):
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) < 3:
            continue

        school = next(
            (part for part in parts if re.search(r"大学|学院|学校", part)), ""
        )
        degree = next(
            (part for part in parts if re.fullmatch(degree_pattern, part)), ""
        )
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
    period_pattern = (
        r"\d{4}(?:[./-]\d{1,2})?\s*[-至~—]\s*(?:\d{4}(?:[./-]\d{1,2})?|至今)"
    )
    section_text = _extract_between_sections(
        raw_text,
        "项目经历",
        ["资格证书", "专业技能", "教育经历", "工作经历", "个人优势"],
    )

    for line in _lines(raw_text):
        if "|" not in line or not re.search(period_pattern, line):
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) < 2 or re.search(r"大学|学院", parts[0]):
            continue
        projects.append(
            {
                "name": parts[0],
                "role": parts[1],
                "description": section_text[:800] if section_text else "",
            }
        )
        break

    if not projects and section_text:
        first_line = _lines(section_text)[0] if _lines(section_text) else ""
        projects.append(
            {"name": first_line, "role": "", "description": section_text[:800]}
        )
    elif not projects and re.search(r"项目经历|项目经验|项目", raw_text):
        projects.append({"name": "", "role": "", "description": ""})
    return projects


def _extract_skills(raw_text: str) -> list[str]:
    skill_line = _first_match(r"(?:技能|专业技能|技术栈)[:：]\s*([^\n]+)", raw_text)
    if skill_line:
        return [
            item.strip()
            for item in re.split(r"[,，、/| ]+", skill_line)
            if item.strip()
        ]

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
    return [
        skill
        for skill in known_skills
        if re.search(re.escape(skill), skill_section, re.I)
    ]


def _extract_self_evaluation(raw_text: str) -> str:
    return _extract_between_sections(
        raw_text,
        "个人优势",
        ["教育经历", "项目经历", "工作经历", "专业技能"],
    )[:500]


def fallback_structure(raw_text: str) -> dict[str, Any]:
    """Build a basic structured result without a model call."""
    result = empty_result()
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
        "basic_info": bool(
            resume["basic_info"]["phone"] or resume["basic_info"]["email"] or name
        ),
        "education": bool(resume["education"]),
        "work_experience": bool(resume["work_experience"]),
        "project_experience": bool(resume["project_experience"]),
        "skills": bool(resume["skills"]),
    }
    score = int(
        sum(1 for present in sections_present.values() if present)
        / len(sections_present)
        * 100
    )
    missing = [
        SECTION_NAMES[key] for key, present in sections_present.items() if not present
    ]

    evaluation["completeness_score"] = score
    evaluation["analysis_source"] = "fallback"
    evaluation["overall_summary"] = (
        "当前未配置可用 AI 模型，系统使用确定性规则完成基础结构化。"
        "该结果可用于本地调试，但深度评价、表达改写和岗位导向建议需要配置 "
        "AI_API_KEY、AI_BASE_URL 和 AI_MODEL 后生成。"
    )
    evaluation["strengths"] = [
        label
        for present, label in (
            (sections_present["basic_info"], "基本联系方式清晰"),
            (sections_present["project_experience"], "包含项目经历"),
            (sections_present["skills"], "包含技能描述"),
        )
        if present
    ]
    evaluation["weaknesses"] = [f"缺少{item}" for item in missing]
    evaluation["missing_sections"] = missing
    evaluation["section_reviews"] = [
        {
            "section": "基本信息",
            "score": 80 if sections_present["basic_info"] else 20,
            "comment": (
                "规则检测到手机号、邮箱或姓名等基础信息。"
                if sections_present["basic_info"]
                else "未检测到完整基础信息。"
            ),
        },
        {
            "section": "项目经历",
            "score": 80 if sections_present["project_experience"] else 20,
            "comment": (
                "规则检测到项目经历，可继续用 AI 分析项目表达质量。"
                if sections_present["project_experience"]
                else "未检测到项目经历。"
            ),
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
        "keyword_density_comment": (
            "规则模式只能识别显式技能，配置 AI 后可获得更完整的关键词覆盖分析。"
        ),
    }
    evaluation["ats_readability"] = (
        "规则模式未进行完整 ATS 可读性判断。建议配置 AI 后分析版式层级、"
        "关键词覆盖、项目成果表达和 HR 快速浏览友好度。"
    )
    evaluation["risk_points"] = ["未启用 AI 深度分析，当前仅为基础结构化结果。"]
    evaluation["rewrite_examples"] = []
    return result
