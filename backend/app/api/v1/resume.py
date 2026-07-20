"""Agent 1 简历分析接口。"""
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.services.resume_tasks import analyze_resume_task, resume_task_store, save_uploaded_resume

router = APIRouter()


@router.post("/upload", summary="上传简历并启动分析")
async def upload_resume(background_tasks: BackgroundTasks, file: UploadFile = File(...)) -> dict:
    state = save_uploaded_resume(file)
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
