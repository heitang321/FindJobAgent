"""Agent 3 简历优化任务编排。"""

from __future__ import annotations

from app.agent.resume_optimization_agent import run_resume_optimization_agent
from app.schema.workflow_state import WorkflowState
from app.core.config import settings
from app.services.resume_tasks import resume_task_store


def prepare_optimization_task(task_id: str) -> WorkflowState:
    """校验前置条件，并将任务标记为可后台执行。"""
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)
    if not state.get("structured_resume"):
        raise ValueError("Resume analysis must finish before optimization.")
    if not state.get("job_requirements"):
        raise ValueError("Job analysis must finish before optimization.")
    if not state.get("match_result") and not state.get("gap_report"):
        raise ValueError(
            "Job match result or gap report is required before optimization."
        )

    state["current_stage"] = "optimizing"
    state["error"] = None
    resume_task_store.update(state)
    return state


def optimize_resume_task(task_id: str) -> WorkflowState:
    """运行 Agent 3，并持久化每一次对外发布的状态变化。"""
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)
    return run_resume_optimization_agent(
        state,
        on_state_update=resume_task_store.update,
        use_configured_llm=settings.AI_ANALYSIS_ENABLED,
        max_workers=settings.OPTIMIZATION_MAX_WORKERS,
        output_dir=settings.OPTIMIZATION_OUTPUT_DIR,
    )
