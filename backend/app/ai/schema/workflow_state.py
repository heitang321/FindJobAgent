"""LangGraph 全局工作流状态。

三个 Agent（简历分析 / 岗位匹配 / 简历优化）之间通过此 State 传递数据。
每个 Agent 读取上游字段、写入自己的产出字段。
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict


# 工作流阶段
Stage = Literal["upload", "analyzing", "job_analysis", "optimizing", "done", "error"]


class WorkflowState(TypedDict, total=False):
    """LangGraph 风格的全局状态。

    Agent 1（简历分析）写入: file_path, file_type, converted_file_path,
    raw_text, structured_resume, resume_evaluation。

    Agent 2（岗位匹配）写入: jd_source_type, jd_raw_text, job_requirements,
    match_result, gap_report。

    Agent 3（简历优化）写入: optimized_resume, diff_report, output_file_path,
    optimization_summary。
    """

    # ===== 通用字段 =====
    task_id: str
    current_stage: Stage  # "upload"|"analyzing"|"job_analysis"|"optimizing"|"done"|"error"
    error: str | None

    # ===== Agent 1 产出 =====
    file_path: str
    file_type: str  # "pdf"|"docx"|"doc"|"unknown"
    converted_file_path: str | None
    raw_text: str
    structured_resume: dict[str, Any]
    resume_evaluation: dict[str, Any]

    # ===== Agent 2 产出 =====
    jd_url: str  # 招聘职位详情页 URL
    jd_source_type: Literal["text", "url"]
    jd_raw_text: str
    job_requirements: dict[str, Any]
    match_result: dict[str, Any]
    gap_report: dict[str, Any]

    # ===== Agent 3 产出 =====
    optimized_resume: dict[str, Any]
    diff_report: dict[str, Any]
    output_file_path: str | None
    optimization_summary: dict[str, Any]


def initial_workflow_state(task_id: str, file_path: str) -> WorkflowState:
    """创建上传完成后的最小初始状态。"""
    return {
        "task_id": task_id,
        "current_stage": "upload",
        "error": None,
        # Agent 1
        "file_path": file_path,
        "file_type": "unknown",
        "converted_file_path": None,
        "raw_text": "",
        "structured_resume": {},
        "resume_evaluation": {},
        # Agent 2
        "jd_url": "",
        "jd_source_type": "text",
        "jd_raw_text": "",
        "job_requirements": {},
        "match_result": {},
        "gap_report": {},
        # Agent 3
        "optimized_resume": {},
        "diff_report": {},
        "output_file_path": None,
        "optimization_summary": {},
    }
"""Shared workflow state passed between resume/job/optimization agents."""
from typing import Any, Literal, TypedDict


Stage = Literal["upload", "analyzing", "job_analysis", "optimizing", "done", "error"]


class WorkflowState(TypedDict, total=False):
    """LangGraph-style state for the full resume optimization workflow.

    Agent nodes read upstream fields and write their own outputs. The current
    implementation runs Agent 1 linearly, while keeping the state shape ready
    for a future LangGraph graph.
    """

    # Common
    task_id: str
    current_stage: Stage
    error: str | None

    # Agent 1 output
    file_path: str
    file_type: str
    converted_file_path: str | None
    raw_text: str
    structured_resume: dict[str, Any]
    resume_evaluation: dict[str, Any]

    # Agent 2 output
    jd_url: str  # Job detail page URL
    jd_source_type: Literal["text", "url"]
    jd_raw_text: str
    job_requirements: dict[str, Any]
    match_result: dict[str, Any]
    gap_report: dict[str, Any]

    # Agent 3 output
    optimized_resume: dict[str, Any]
    diff_report: dict[str, Any]
    output_file_path: str | None
    optimization_summary: dict[str, Any]


def initial_workflow_state(task_id: str, file_path: str) -> WorkflowState:
    """Create the minimal state written after upload."""
    return {
        "task_id": task_id,
        "current_stage": "upload",
        "error": None,
        "file_path": file_path,
        "file_type": "unknown",
        "converted_file_path": None,
        "raw_text": "",
        "structured_resume": {},
        "resume_evaluation": {},
        "jd_url": "",
        "jd_source_type": "text",
        "jd_raw_text": "",
        "job_requirements": {},
        "match_result": {},
        "gap_report": {},
        "optimized_resume": {},
        "diff_report": {},
        "output_file_path": None,
        "optimization_summary": {},
    }
