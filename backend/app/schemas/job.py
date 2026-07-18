"""Pydantic contracts for Agent 2 job analysis."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class JobAnalysisRequest(BaseModel):
    """前端提交 JD URL 的请求体。"""

    jd_url: str = Field(..., description="招聘职位详情页 URL，例如 https://www.zhaopin.com/jobdetail/CC....htm")


class JobAnalysisResponse(BaseModel):
    """Agent 2 跑完返回的匹配结果和 gap 报告。"""

    task_id: str
    current_stage: str
    error: str | None = None
    jd_raw_text: str = ""
    job_requirements: dict[str, Any] = Field(default_factory=dict)
    match_result: dict[str, Any] = Field(default_factory=dict)
    gap_report: dict[str, Any] = Field(default_factory=dict)
