"""Agent 3 优化触发、结果查询和下载接口。

支持多版本优化策略：一次触发生成保守版、均衡版、激进版三个版本。
用户可在前端对比选择最满意的版本下载。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser
from app.schemas.optimization import (
    OptimizationResultResponse,
    OptimizationTriggerResponse,
    OptimizationVersionData,
    STRATEGY_LABELS,
)
from app.services.optimization_tasks import (
    optimize_resume_task,
    prepare_optimization_task,
)
from app.services.resume_tasks import resume_task_store


router = APIRouter()


def _task_or_404(task_id: str, user_id: str) -> dict:
    state = resume_task_store.get(task_id)
    if state is None or state.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Optimization task not found")
    return state


@router.post(
    "/{task_id}",
    response_model=OptimizationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="触发简历优化（生成保守/均衡/激进三个版本）",
)
async def trigger_optimization(
    task_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser,
) -> OptimizationTriggerResponse:
    _task_or_404(task_id, user["id"])
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
    summary="获取优化结果（含多版本对比）",
)
async def get_optimization_result(
    task_id: str,
    user: CurrentUser,
) -> OptimizationResultResponse:
    state = _task_or_404(task_id, user["id"])
    output_path = state.get("output_file_path")

    # 构建多版本列表
    versions_raw = state.get("optimization_versions") or {}
    versions: list[OptimizationVersionData] = []
    for strategy_key in ("conservative", "balanced", "aggressive"):
        v = versions_raw.get(strategy_key)
        if not v:
            continue
        versions.append(
            OptimizationVersionData(
                strategy=v.get("strategy", strategy_key),
                label=v.get("label", STRATEGY_LABELS.get(strategy_key, strategy_key)),
                description=v.get("description", ""),
                optimized_resume=v.get("optimized_resume") or {},
                diff_report=v.get("diff_report") or {},
                optimization_summary=v.get("optimization_summary") or {},
                download_ready=bool(
                    v.get("output_file_path")
                    and Path(v["output_file_path"]).is_file()
                ),
                error=v.get("error"),
            )
        )

    return OptimizationResultResponse(
        task_id=task_id,
        current_stage=state["current_stage"],
        error=state.get("error"),
        optimized_resume=state.get("optimized_resume") or {},
        diff_report=state.get("diff_report") or {},
        optimization_summary=state.get("optimization_summary") or {},
        download_ready=bool(output_path and Path(output_path).is_file()),
        optimization_versions=versions,
    )


@router.get("/{task_id}/download", summary="下载优化后的 Word 简历（默认均衡版）")
async def download_optimized_resume(
    task_id: str,
    user: CurrentUser,
    strategy: str = Query("balanced", description="优化策略: conservative/balanced/aggressive"),
) -> FileResponse:
    state = _task_or_404(task_id, user["id"])

    # 如果指定了策略，从版本数据中取对应路径
    if strategy != "balanced":
        versions = state.get("optimization_versions") or {}
        version = versions.get(strategy)
        if not version:
            raise HTTPException(
                status_code=404,
                detail=f"Optimization version '{strategy}' not found",
            )
        output_path = version.get("output_file_path")
    else:
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
