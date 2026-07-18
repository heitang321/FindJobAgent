"""Task orchestration for Agent 3 resume optimization."""

from __future__ import annotations

from app.agent.resume_optimization_agent import run_resume_optimization_agent
from app.schemas.workflow_state import WorkflowState
from app.core.config import settings
from app.services.resume_tasks import resume_task_store


def prepare_optimization_task(task_id: str) -> WorkflowState:
    """Validate prerequisites and mark a task ready for background execution."""
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)
    if not state.get("structured_resume"):
        raise ValueError("Resume analysis must finish before optimization.")
    if not state.get("job_requirements"):
        raise ValueError("Job analysis must finish before optimization.")

    state["current_stage"] = "optimizing"
    state["error"] = None
    resume_task_store.update(state)
    return state


def optimize_resume_task(task_id: str) -> WorkflowState:
    """Run Agent 3 and persist every published state transition."""
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
