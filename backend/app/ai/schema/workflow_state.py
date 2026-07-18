"""Shared workflow state passed between the three resume agents."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


Stage = Literal["upload", "analyzing", "job_analysis", "optimizing", "done", "error"]


class WorkflowState(TypedDict, total=False):
    """Global state whose fields are owned by one agent stage each."""

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
    """Create the state written immediately after a resume upload."""
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
