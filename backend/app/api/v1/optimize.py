"""Agent 3 optimization trigger, result, and download endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import FileResponse

from app.schemas.optimization import (
    OptimizationResultResponse,
    OptimizationTriggerResponse,
)
from app.services.optimization_tasks import (
    optimize_resume_task,
    prepare_optimization_task,
)
from app.services.resume_tasks import resume_task_store


router = APIRouter()


def _task_or_404(task_id: str) -> dict:
    state = resume_task_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Optimization task not found")
    return state


@router.post(
    "/{task_id}",
    response_model=OptimizationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="触发简历优化",
)
async def trigger_optimization(
    task_id: str, background_tasks: BackgroundTasks
) -> OptimizationTriggerResponse:
    try:
        state = prepare_optimization_task(task_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail="Optimization task not found"
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    background_tasks.add_task(optimize_resume_task, task_id)
    return OptimizationTriggerResponse(
        task_id=task_id,
        current_stage=state["current_stage"],
    )


@router.get(
    "/{task_id}/result",
    response_model=OptimizationResultResponse,
    summary="获取优化结果和对比报告",
)
async def get_optimization_result(task_id: str) -> OptimizationResultResponse:
    state = _task_or_404(task_id)
    output_path = state.get("output_file_path")
    return OptimizationResultResponse(
        task_id=task_id,
        current_stage=state["current_stage"],
        error=state.get("error"),
        optimized_resume=state.get("optimized_resume") or {},
        diff_report=state.get("diff_report") or {},
        optimization_summary=state.get("optimization_summary") or {},
        download_ready=bool(output_path and Path(output_path).is_file()),
    )


@router.get("/{task_id}/download", summary="下载优化后的 Word 简历")
async def download_optimized_resume(task_id: str) -> FileResponse:
    state = _task_or_404(task_id)
    output_path = state.get("output_file_path")
    if not output_path or not Path(output_path).is_file():
        raise HTTPException(status_code=409, detail="Optimized resume is not ready")

    path = Path(output_path)
    return FileResponse(
        path=path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=path.name,
    )
