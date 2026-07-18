"""Pydantic contracts for Agent 3 resume optimization."""

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
    """One explainable change made to a resume section."""

    type: ChangeType
    description: str


class SectionRewriteRequest(BaseModel):
    """Input contract for one independent section rewrite."""

    section_type: SectionType
    original_content: str
    evidence_context: str = ""
    gap_report: dict[str, Any] = Field(default_factory=dict)
    job_requirements: dict[str, Any] = Field(default_factory=dict)
    job_keywords: list[str] = Field(default_factory=list)


class SectionRewriteResult(BaseModel):
    """Structured output returned by Tool 3.1."""

    section_type: SectionType
    original_content: str
    rewritten_content: str
    change_reason: str
    changes: list[SectionChange] = Field(default_factory=list)


class DiffSpan(BaseModel):
    """A highlightable text fragment for the comparison view."""

    type: Literal["equal", "added", "modified", "removed"]
    original_text: str = ""
    optimized_text: str = ""


class SectionDiff(BaseModel):
    """Original/optimized comparison for one section occurrence."""

    section_type: str
    section_index: int
    original_content: str
    optimized_content: str
    changed: bool
    change_reason: str = ""
    changes: list[SectionChange] = Field(default_factory=list)
    spans: list[DiffSpan] = Field(default_factory=list)


class DiffReport(BaseModel):
    """Frontend-ready comparison report produced by Tool 3.4."""

    sections: list[SectionDiff] = Field(default_factory=list)


class OptimizationSummary(BaseModel):
    """Aggregate counts and labels shown above the comparison view."""

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
