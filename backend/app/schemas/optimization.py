"""Agent 3 简历优化的 Pydantic 数据契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SectionType = Literal[
    "work_experience",
    "project_experience",
    "self_evaluation",
    "skills",
]
ChangeType = Literal["added", "modified", "removed"]


class SectionChange(BaseModel):
    """一次可解释的简历段落修改。"""

    type: ChangeType
    description: str


class SectionRewriteRequest(BaseModel):
    """单个独立段落改写的输入契约。"""

    section_type: SectionType
    original_content: str
    evidence_context: str = ""
    gap_report: dict[str, Any] = Field(default_factory=dict)
    job_requirements: dict[str, Any] = Field(default_factory=dict)
    job_keywords: list[str] = Field(default_factory=list)


class SectionRewriteResult(BaseModel):
    """Tool 3.1 返回的结构化输出。"""

    section_type: SectionType
    original_content: str
    rewritten_content: str
    change_reason: str
    changes: list[SectionChange] = Field(default_factory=list)


class DiffSpan(BaseModel):
    """对比视图中可高亮的一段文本。"""

    type: Literal["equal", "added", "modified", "removed"]
    original_text: str = ""
    optimized_text: str = ""


class SectionDiff(BaseModel):
    """单个段落实例的原文与优化后对比。"""

    section_type: str
    section_index: int
    original_content: str
    optimized_content: str
    changed: bool
    change_reason: str = ""
    changes: list[SectionChange] = Field(default_factory=list)
    spans: list[DiffSpan] = Field(default_factory=list)


class DiffReport(BaseModel):
    """Tool 3.4 生成的前端可直接渲染的对比报告。"""

    sections: list[SectionDiff] = Field(default_factory=list)


class OptimizationSummary(BaseModel):
    """对比视图顶部展示的汇总数量与标签。"""

    rewritten_sections: list[str] = Field(default_factory=list)
    unchanged_sections: list[str] = Field(default_factory=list)
    added_count: int = 0
    modified_count: int = 0
    removed_count: int = 0
    added_keywords: list[str] = Field(default_factory=list)


class OptimizationTriggerResponse(BaseModel):
    task_id: str
    current_stage: str


class OptimizationResultResponse(BaseModel):
    task_id: str
    current_stage: str
    error: str | None = None
    optimized_resume: dict[str, Any] = Field(default_factory=dict)
    diff_report: dict[str, Any] = Field(default_factory=dict)
    optimization_summary: dict[str, Any] = Field(default_factory=dict)
    download_ready: bool = False
