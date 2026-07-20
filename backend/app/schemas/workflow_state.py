"""LangGraph 全局工作流状态。

三个 Agent（简历分析 / 岗位匹配 / 简历优化）之间通过此 State 传递数据。
每个 Agent 读取上游字段、写入自己的产出字段。

并发图（A1 ‖ A2 前缀 → A2.4 matcher）中，task_id / current_stage / error
会被多个并发节点同时返回。LangGraph 默认对同一 key 接收多个值会报错
"Can receive only one value per step"。解决方式：用 Annotated[type, reducer]
给这三个共享字段配 reducer，告诉 LangGraph 怎么合并多个分支的写入。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


# 工作流阶段
Stage = Literal["upload", "analyzing", "job_analysis", "optimizing", "done", "error"]


# ===== LangGraph channel reducer =====
# 并发节点（A1 / A2 前缀）同时返回 state 时，用这些 reducer 合并共享字段。


def keep_last(old: Any, new: Any) -> Any:
    """通用 reducer：后写覆盖先写。task_id 在所有分支都是同一个值，谁后写都一样。"""
    return new if new is not None else old


def prefer_error_stage(old: str | None, new: str | None) -> str | None:
    """合并 current_stage：任一分支 error → error；否则取后写值。

    A1 成功 (done) 但 A2 前缀失败 (error) 时，整体应记为 error。
    """
    if old == "error" or new == "error":
        return "error"
    return new if new is not None else old


def merge_error(old: str | None, new: str | None) -> str | None:
    """合并 error：任一非 None 则保留；两个都有则用分号拼接保留完整信息。"""
    if old and new:
        return f"{old}; {new}"
    return new if new is not None else old


class WorkflowState(TypedDict, total=False):
    """LangGraph 风格的全局状态。

    Agent 1（简历分析）写入: file_path, file_type, converted_file_path,
    raw_text, structured_resume, resume_evaluation。

    Agent 2（岗位匹配）写入: jd_source_type, jd_raw_text, job_requirements,
    match_result, gap_report。

    Agent 3（简历优化）写入: optimized_resume, diff_report, output_file_path,
    optimization_summary。

    task_id / current_stage / error 加了 Annotated reducer：
    A1 和 A2 前缀并发返回 state 时，LangGraph 用 reducer 合并这三个共享字段，
    而不是抛 "Can receive only one value per step"。
    """

    # ===== 通用字段（带 reducer，支持并发节点同时返回） =====
    task_id: Annotated[str, keep_last]
    user_id: Annotated[str, keep_last]
    current_stage: Annotated[Stage, prefer_error_stage]
    error: Annotated[str | None, merge_error]

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
    # 岗位搜索结果（POST /job/{task_id}/search 写入，供前端展示卡片列表）
    job_search_results: list[dict[str, Any]]
    # 用户从搜索结果中选中的岗位详情页 URL（供后续 analyze 复用）
    selected_jd_url: str

    # ===== Agent 3 产出 =====
    optimized_resume: dict[str, Any]
    diff_report: dict[str, Any]
    output_file_path: str | None
    optimization_summary: dict[str, Any]


def initial_workflow_state(
    task_id: str,
    file_path: str,
    user_id: str = "",
) -> WorkflowState:
    """创建上传完成后的最小初始状态。"""
    return {
        "task_id": task_id,
        "user_id": user_id,
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
        "job_search_results": [],
        "selected_jd_url": "",
        # Agent 3
        "optimized_resume": {},
        "diff_report": {},
        "output_file_path": None,
        "optimization_summary": {},
    }
