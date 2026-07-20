"""Agent 1 简历分析接口。"""
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.api.deps import CurrentUser
from app.services.resume_tasks import analyze_resume_task, resume_task_store, save_uploaded_resume

router = APIRouter()


@router.get("/history", summary="获取当前用户的简历任务历史")
async def get_resume_history(user: CurrentUser) -> dict:
    """返回当前登录用户的简历任务列表，按创建时间倒序。"""
    tasks = resume_task_store.list_by_user(user["id"])
    return {"tasks": tasks, "total": len(tasks)}


@router.post("/upload", summary="上传简历并启动分析")
async def upload_resume(
    background_tasks: BackgroundTasks,
    user: CurrentUser,
    file: UploadFile = File(...),
) -> dict:
    state = save_uploaded_resume(file, user_id=user["id"])
    background_tasks.add_task(analyze_resume_task, state["task_id"])
    return {
        "task_id": state["task_id"],
        "file_type": state["file_type"],
        "current_stage": state["current_stage"],
    }


@router.get("/{task_id}/analysis", summary="获取简历结构化分析结果")
async def get_resume_analysis(task_id: str) -> dict:
    state = resume_task_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Resume analysis task not found")

    return {
        "task_id": state["task_id"],
        "current_stage": state["current_stage"],
        "error": state.get("error"),
        "file_type": state.get("file_type", "unknown"),
        "converted_file_path": state.get("converted_file_path"),
        "structured_resume": state.get("structured_resume", {}),
        "evaluation": state.get("resume_evaluation", {}),
    }
