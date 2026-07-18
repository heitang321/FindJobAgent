"""Normalized result templates for the resume-structuring module."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


EMPTY_STRUCTURED_RESUME: dict[str, Any] = {
    "basic_info": {"name": "", "phone": "", "email": "", "location": ""},
    "education": [],
    "work_experience": [],
    "project_experience": [],
    "skills": [],
    "self_evaluation": "",
}


def empty_result() -> dict[str, Any]:
    """Return a fresh result with every documented field present."""
    return {
        "structured_resume": deepcopy(EMPTY_STRUCTURED_RESUME),
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


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize untrusted LLM or fallback data to the public result shape."""
    result = empty_result()
    structured = data.get("structured_resume") or {}
    evaluation = data.get("evaluation") or {}

    basic_info = structured.get("basic_info") or {}
    for key in ("name", "phone", "email", "location"):
        result["structured_resume"]["basic_info"][key] = str(basic_info.get(key) or "")

    for key in ("education", "work_experience", "project_experience", "skills"):
        value = structured.get(key)
        result["structured_resume"][key] = value if isinstance(value, list) else []

    result["structured_resume"]["self_evaluation"] = str(
        structured.get("self_evaluation") or ""
    )

    for key in ("analysis_source", "overall_summary", "ats_readability", "llm_error"):
        result["evaluation"][key] = str(evaluation.get(key) or "")

    score = evaluation.get("completeness_score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    result["evaluation"]["completeness_score"] = max(0, min(100, score))

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
        detected = keyword_analysis.get("detected_keywords")
        missing = keyword_analysis.get("missing_keywords")
        result["evaluation"]["keyword_analysis"] = {
            "detected_keywords": detected if isinstance(detected, list) else [],
            "missing_keywords": missing if isinstance(missing, list) else [],
            "keyword_density_comment": str(
                keyword_analysis.get("keyword_density_comment") or ""
            ),
        }

    return result
