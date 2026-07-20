"""Agent 1 简历分析接口。

重构后上传不再触发 BackgroundTasks 跑 A1：避免和 LangGraph 图的 A1 节点
双重调用 LLM API 导致限流超时。A1 由 LangGraph 图统一跑
（POST /job/{task_id}/analyze 触发 A1‖A2前缀 并发）。
"""

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser
from app.services.resume_tasks import (
    ResumeUploadTooLarge,
    resume_task_store,
    save_uploaded_resume,
)

router = APIRouter()


@router.post("/upload", summary="上传简历，等待 JD URL 后由 LangGraph 图统一跑 A1+A2")
async def upload_resume(user: CurrentUser, file: UploadFile = File(...)) -> dict:
    """上传简历文件，保存到 uploads/resumes/<task_id>/，初始化 state。

    重构后**不再触发 BackgroundTasks 跑 A1**：

    - 之前前端是"等 A1 跑完再提交 JD URL"，BackgroundTasks 跑 A1 是必要的
    - 现在前端改为"上传后立即 job_input 让用户提交 JD URL"，如果 BackgroundTasks
      还在跑 A1，用户提交 JD URL 时 LangGraph 图的 A1 节点会和 BackgroundTasks
      的 A1 双重调用 LLM API，限流排队导致超时
    - 手动提交 JD 时由 LangGraph 图统一跑（POST /job/{task_id}/analyze 触发
      A1‖A2前缀 并发）
    - 自动推荐岗位时，POST /job/{task_id}/search 会按需先运行 A1

    返回 task_id 让前端后续轮询 /resume/{task_id}/analysis 和提交
    /job/{task_id}/analyze。
    """
    try:
        state = await asyncio.to_thread(save_uploaded_resume, file, user["id"])
    except ResumeUploadTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {
        "task_id": state["task_id"],
        "file_type": state["file_type"],
        "current_stage": state["current_stage"],
    }


@router.get("/{task_id}/analysis", summary="获取简历结构化分析结果（含岗位搜索结果）")
async def get_resume_analysis(task_id: str, user: CurrentUser) -> dict:
    state = resume_task_store.get(task_id)
    if state is None or state.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Resume analysis task not found")

    return {
        "task_id": state["task_id"],
        "current_stage": state.get("current_stage"),
        "error": state.get("error"),
        "file_type": state.get("file_type", "unknown"),
        "converted_file_path": state.get("converted_file_path"),
        "structured_resume": state.get("structured_resume", {}),
        "evaluation": state.get("resume_evaluation", {}),
        # 岗位搜索结果（POST /job/{task_id}/search 写入）
        "job_search_results": state.get("job_search_results", []),
        "selected_jd_url": state.get("selected_jd_url", ""),
    }
