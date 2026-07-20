"""Agent 1 简历分析使用的 MySQL 任务服务。

WorkflowState 的所有字段持久化到 resume_tasks 表，
后台 Agent 执行时通过 on_state_update 回调实时写入数据库。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select

from app.agent.resume_analysis_agent import run_resume_analysis_agent
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.resume_task import ResumeTask
from app.schema.workflow_state import WorkflowState, initial_workflow_state
from app.tools.file_type_detector import file_type_detector


# WorkflowState 字段与 ResumeTask 列的映射
_STATE_COLUMN_MAP: dict[str, str] = {
    "task_id": "task_id",
    "current_stage": "current_stage",
    "error": "error",
    "file_path": "file_path",
    "file_type": "file_type",
    "converted_file_path": "converted_file_path",
    "raw_text": "raw_text",
    "structured_resume": "structured_resume",
    "resume_evaluation": "resume_evaluation",
    "jd_source_type": "jd_source_type",
    "jd_raw_text": "jd_raw_text",
    "job_requirements": "job_requirements",
    "match_result": "match_result",
    "gap_report": "gap_report",
    "optimized_resume": "optimized_resume",
    "diff_report": "diff_report",
    "output_file_path": "output_file_path",
    "optimization_summary": "optimization_summary",
}


def _state_to_orm(state: WorkflowState, task: ResumeTask) -> None:
    """将 WorkflowState 字典字段写入 ORM 对象。"""
    for state_key, col_name in _STATE_COLUMN_MAP.items():
        value = state.get(state_key)
        if value is not None:
            # JSON 列需要确保是 dict/list 类型
            if col_name in (
                "structured_resume",
                "resume_evaluation",
                "job_requirements",
                "match_result",
                "gap_report",
                "optimized_resume",
                "diff_report",
                "optimization_summary",
            ) and isinstance(value, str):
                value = json.loads(value)
            setattr(task, col_name, value)


def _orm_to_state(task: ResumeTask) -> WorkflowState:
    """将 ORM 对象转换为 WorkflowState 字典。"""
    return WorkflowState(
        task_id=task.task_id,
        current_stage=task.current_stage,
        error=task.error,
        file_path=task.file_path or "",
        file_type=task.file_type or "unknown",
        converted_file_path=task.converted_file_path,
        raw_text=task.raw_text or "",
        structured_resume=task.structured_resume or {},
        resume_evaluation=task.resume_evaluation or {},
        jd_url="",  # jd_url 不在数据库中，保持兼容
        jd_source_type=task.jd_source_type or "text",
        jd_raw_text=task.jd_raw_text or "",
        job_requirements=task.job_requirements or {},
        match_result=task.match_result or {},
        gap_report=task.gap_report or {},
        optimized_resume=task.optimized_resume or {},
        diff_report=task.diff_report or {},
        output_file_path=task.output_file_path,
        optimization_summary=task.optimization_summary or {},
    )


class ResumeTaskStore:
    """基于 MySQL 的任务存储。

    WorkflowState 的所有字段映射到 resume_tasks 表的列。
    Agent 执行时通过 update() 回调实时持久化状态变化。
    """

    def set(self, task_id: str, state: WorkflowState) -> None:
        """插入或替换一条任务记录。"""
        with SessionLocal() as db:
            existing = db.get(ResumeTask, task_id)
            if existing is None:
                task = ResumeTask(task_id=task_id)
                _state_to_orm(state, task)
                db.add(task)
            else:
                _state_to_orm(state, existing)
            db.commit()

    def get(self, task_id: str) -> WorkflowState | None:
        """根据 task_id 获取任务状态。"""
        with SessionLocal() as db:
            task = db.get(ResumeTask, task_id)
            if task is None:
                return None
            return _orm_to_state(task)

    def update(self, state: WorkflowState) -> None:
        """更新任务状态（Agent 回调使用）。"""
        self.set(state["task_id"], state)

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        """查询某用户的简历任务列表（精简字段，不含大文本列）。

        返回按创建时间倒序排列的任务摘要列表。
        """
        from sqlalchemy import desc

        with SessionLocal() as db:
            stmt = (
                select(
                    ResumeTask.task_id,
                    ResumeTask.current_stage,
                    ResumeTask.file_type,
                    ResumeTask.error,
                    ResumeTask.created_at,
                    ResumeTask.updated_at,
                    ResumeTask.structured_resume,
                    ResumeTask.match_result,
                    ResumeTask.optimization_summary,
                )
                .where(ResumeTask.user_id == user_id)
                .order_by(desc(ResumeTask.created_at))
                .limit(limit)
            )
            rows = db.execute(stmt).all()

        result: list[dict] = []
        for row in rows:
            structured = row.structured_resume or {}
            basic = structured.get("basic_info", {}) if isinstance(structured, dict) else {}
            match = row.match_result or {}
            match_score = match.get("overall_score") if isinstance(match, dict) else None
            opt_summary = row.optimization_summary or {}
            has_optimized = bool(
                opt_summary.get("added_count")
                or opt_summary.get("modified_count")
                or opt_summary.get("rewritten_sections")
            ) if isinstance(opt_summary, dict) else False

            result.append({
                "task_id": row.task_id,
                "current_stage": row.current_stage,
                "file_type": row.file_type or "unknown",
                "error": row.error,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "resume_name": basic.get("name", "") if isinstance(basic, dict) else "",
                "match_score": match_score,
                "has_optimized": has_optimized,
            })
        return result


resume_task_store = ResumeTaskStore()


def _safe_filename(filename: str) -> str:
    name = Path(filename or "resume").name
    return name.replace("/", "_").replace("\\", "_")


def save_uploaded_resume(file: UploadFile, user_id: str | None = None) -> WorkflowState:
    """保存上传的简历文件，创建初始 WorkflowState 并写入数据库。

    Parameters
    ----------
    file:
        FastAPI UploadFile 对象。
    user_id:
        当前登录用户 ID，用于关联任务归属。
    """
    task_id = uuid4().hex
    upload_dir = Path(settings.RESUME_UPLOAD_DIR) / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    target = upload_dir / _safe_filename(file.filename or "resume")
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    state = initial_workflow_state(task_id=task_id, file_path=str(target))
    state["file_type"] = file_type_detector(str(target))["file_type"]
    # 关联用户 ID 到数据库记录
    with SessionLocal() as db:
        existing = db.get(ResumeTask, task_id)
        if existing is None:
            task = ResumeTask(task_id=task_id, user_id=user_id)
            _state_to_orm(state, task)
            db.add(task)
            db.commit()
        else:
            if user_id:
                existing.user_id = user_id
            _state_to_orm(state, existing)
            db.commit()
    return state


def analyze_resume_task(task_id: str) -> WorkflowState:
    """后台执行 Agent 1 简历分析，每次状态变化持久化到数据库。"""
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)
    return run_resume_analysis_agent(
        state,
        on_state_update=resume_task_store.update,
        use_configured_llm=settings.AI_ANALYSIS_ENABLED,
    )
