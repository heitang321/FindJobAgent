"""Agent 1 简历上传、历史记录和分析结果接口。

上传阶段只保存文件和初始化任务。Agent 1 由手动 JD 分析或自动岗位推荐按需
触发，避免上传后台任务和 LangGraph 并发图重复调用 LLM。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser
from app.services.resume_tasks import (
    ResumeUploadTooLarge,
    resume_task_store,
    save_uploaded_resume,
)

router = APIRouter()


@router.get("/history", summary="获取当前用户的简历任务历史")
async def get_resume_history(user: CurrentUser) -> dict:
    """返回当前登录用户的简历任务列表，按创建时间倒序。"""
    tasks = await asyncio.to_thread(resume_task_store.list_by_user, user["id"])
    return {"tasks": tasks, "total": len(tasks)}


@router.post("/upload", summary="上传简历，后续按需执行 Agent 1")
async def upload_resume(user: CurrentUser, file: UploadFile = File(...)) -> dict:
    """保存 PDF/DOCX 简历并初始化任务，不在上传阶段调用 LLM。"""
    try:
        state = await asyncio.to_thread(
            save_uploaded_resume,
            file,
            user["id"],
        )
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
    state = await asyncio.to_thread(resume_task_store.get, task_id)
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
        "job_search_results": state.get("job_search_results", []),
        "selected_jd_url": state.get("selected_jd_url", ""),
    }


@router.delete("/{task_id}", summary="删除指定的简历任务记录")
async def delete_resume_task(task_id: str, user: CurrentUser) -> dict:
    """删除简历任务及其关联文件，校验用户归属。"""
    deleted = await asyncio.to_thread(resume_task_store.delete, task_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Resume task not found or no permission")
    return {"task_id": task_id, "deleted": True}
