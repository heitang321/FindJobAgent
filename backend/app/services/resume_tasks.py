"""简历任务存储与上传服务。

生产环境使用 MySQL 持久化完整 WorkflowState；测试环境使用进程内实现。
两种实现共享相同接口，并对 LangGraph 并发分支发布的 partial state 做字段级合并。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import desc, select

from app.agent.resume_analysis_agent import run_resume_analysis_agent
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.resume_task import ResumeTask
from app.schemas.workflow_state import WorkflowState, initial_workflow_state
from app.tools.file_type_detector import file_type_detector

_JSON_STATE_FIELDS = {
    "structured_resume",
    "resume_evaluation",
    "job_requirements",
    "match_result",
    "gap_report",
    "job_search_results",
    "optimized_resume",
    "diff_report",
    "optimization_summary",
}

_STATE_COLUMN_MAP: dict[str, str] = {
    "task_id": "task_id",
    "user_id": "user_id",
    "current_stage": "current_stage",
    "error": "error",
    "file_path": "file_path",
    "file_type": "file_type",
    "converted_file_path": "converted_file_path",
    "raw_text": "raw_text",
    "structured_resume": "structured_resume",
    "resume_evaluation": "resume_evaluation",
    "jd_url": "jd_url",
    "jd_source_type": "jd_source_type",
    "jd_raw_text": "jd_raw_text",
    "job_requirements": "job_requirements",
    "match_result": "match_result",
    "gap_report": "gap_report",
    "job_search_results": "job_search_results",
    "selected_jd_url": "selected_jd_url",
    "optimized_resume": "optimized_resume",
    "diff_report": "diff_report",
    "output_file_path": "output_file_path",
    "optimization_summary": "optimization_summary",
}


def _state_to_orm(state: WorkflowState, task: ResumeTask) -> None:
    """把 state 中实际存在的字段合并到 ORM 对象。"""
    for state_key, column_name in _STATE_COLUMN_MAP.items():
        if state_key not in state:
            continue
        value = state[state_key]
        if state_key in _JSON_STATE_FIELDS:
            if isinstance(value, str):
                value = json.loads(value)
            elif value is None:
                value = [] if state_key == "job_search_results" else {}
        setattr(task, column_name, value)


def _orm_to_state(task: ResumeTask) -> WorkflowState:
    """把 ORM 任务恢复成 API/LangGraph 使用的完整状态。"""
    return WorkflowState(
        task_id=task.task_id,
        user_id=task.user_id or "",
        current_stage=task.current_stage,
        error=task.error,
        file_path=task.file_path or "",
        file_type=task.file_type or "unknown",
        converted_file_path=task.converted_file_path,
        raw_text=task.raw_text or "",
        structured_resume=task.structured_resume or {},
        resume_evaluation=task.resume_evaluation or {},
        jd_url=task.jd_url or "",
        jd_source_type=task.jd_source_type or "text",
        jd_raw_text=task.jd_raw_text or "",
        job_requirements=task.job_requirements or {},
        match_result=task.match_result or {},
        gap_report=task.gap_report or {},
        job_search_results=task.job_search_results or [],
        selected_jd_url=task.selected_jd_url or "",
        optimized_resume=task.optimized_resume or {},
        diff_report=task.diff_report or {},
        output_file_path=task.output_file_path,
        optimization_summary=task.optimization_summary or {},
    )


def _history_item(state: WorkflowState) -> dict:
    structured = state.get("structured_resume") or {}
    basic = structured.get("basic_info", {}) if isinstance(structured, dict) else {}
    match = state.get("match_result") or {}
    summary = state.get("optimization_summary") or {}
    has_optimized = bool(
        isinstance(summary, dict)
        and (
            summary.get("added_count")
            or summary.get("modified_count")
            or summary.get("rewritten_sections")
        )
    )
    return {
        "task_id": state["task_id"],
        "current_stage": state.get("current_stage"),
        "file_type": state.get("file_type", "unknown"),
        "error": state.get("error"),
        "created_at": None,
        "updated_at": None,
        "resume_name": basic.get("name", "") if isinstance(basic, dict) else "",
        "match_score": (
            match.get("overall_score") if isinstance(match, dict) else None
        ),
        "has_optimized": has_optimized,
    }


class MySQLResumeTaskStore:
    """基于 MySQL 的 WorkflowState 持久化。"""

    def set(self, task_id: str, state: WorkflowState) -> None:
        with SessionLocal() as database:
            task = database.get(ResumeTask, task_id)
            if task is None:
                task = ResumeTask(task_id=task_id)
                database.add(task)
            _state_to_orm(state, task)
            database.commit()

    def get(self, task_id: str) -> WorkflowState | None:
        with SessionLocal() as database:
            task = database.get(ResumeTask, task_id)
            return _orm_to_state(task) if task is not None else None

    def update(self, state: WorkflowState) -> None:
        """字段级合并 LangGraph partial state。"""
        self.set(state["task_id"], state)

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        with SessionLocal() as database:
            statement = (
                select(ResumeTask)
                .where(ResumeTask.user_id == user_id)
                .order_by(desc(ResumeTask.created_at))
                .limit(limit)
            )
            tasks = database.execute(statement).scalars().all()

        result: list[dict] = []
        for task in tasks:
            item = _history_item(_orm_to_state(task))
            item["created_at"] = (
                task.created_at.isoformat() if task.created_at else None
            )
            item["updated_at"] = (
                task.updated_at.isoformat() if task.updated_at else None
            )
            result.append(item)
        return result

    def delete(self, task_id: str, user_id: str) -> bool:
        """删除指定任务，校验用户归属。返回是否删除成功。"""
        import shutil
        from pathlib import Path

        with SessionLocal() as database:
            task = database.get(ResumeTask, task_id)
            if task is None or task.user_id != user_id:
                return False
            # 删除上传的简历文件
            if task.file_path:
                try:
                    file_dir = Path(task.file_path).parent
                    if file_dir.exists():
                        shutil.rmtree(file_dir, ignore_errors=True)
                except Exception:
                    pass
            if task.output_file_path:
                try:
                    out_file = Path(task.output_file_path)
                    if out_file.exists():
                        out_file.unlink(missing_ok=True)
                except Exception:
                    pass
            database.delete(task)
            database.commit()
            return True


class InMemoryResumeTaskStore:
    """测试使用的线程安全任务存储。"""

    def __init__(self) -> None:
        self._tasks: dict[str, WorkflowState] = {}
        self._lock = Lock()

    def set(self, task_id: str, state: WorkflowState) -> None:
        with self._lock:
            self._tasks[task_id] = dict(state)

    def get(self, task_id: str) -> WorkflowState | None:
        with self._lock:
            state = self._tasks.get(task_id)
            return dict(state) if state is not None else None

    def update(self, state: WorkflowState) -> None:
        with self._lock:
            current = dict(self._tasks.get(state["task_id"], {}))
            current.update(state)
            self._tasks[state["task_id"]] = current

    def list_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            states = [
                dict(state)
                for state in reversed(list(self._tasks.values()))
                if state.get("user_id") == user_id
            ]
        return [_history_item(state) for state in states[:limit]]

    def delete(self, task_id: str, user_id: str) -> bool:
        with self._lock:
            state = self._tasks.get(task_id)
            if state is None or state.get("user_id") != user_id:
                return False
            del self._tasks[task_id]
            return True


resume_task_store = (
    InMemoryResumeTaskStore() if settings.TESTING else MySQLResumeTaskStore()
)


def _safe_filename(filename: str) -> str:
    return Path(filename or "resume").name.replace("/", "_").replace("\\", "_")


class ResumeUploadTooLarge(ValueError):
    """上传文件超过配置上限。"""


def save_uploaded_resume(file: UploadFile, user_id: str) -> WorkflowState:
    """校验并保存 PDF/DOCX，创建带用户归属的初始任务。"""
    task_id = uuid4().hex
    configured_dir = Path(settings.RESUME_UPLOAD_DIR)
    upload_root = (
        configured_dir
        if configured_dir.is_absolute()
        else Path(__file__).resolve().parents[2] / configured_dir
    )
    upload_dir = upload_root / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / _safe_filename(file.filename or "resume")

    size = 0
    try:
        with target.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.RESUME_MAX_UPLOAD_BYTES:
                    raise ResumeUploadTooLarge(
                        "简历文件不能超过 "
                        f"{settings.RESUME_MAX_UPLOAD_BYTES // 1024 // 1024} MB"
                    )
                output.write(chunk)

        file_type = file_type_detector(str(target))["file_type"]
        if file_type not in {"pdf", "docx"}:
            raise ValueError("仅支持有效的 PDF 或 DOCX 简历文件")
    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise

    state = initial_workflow_state(
        task_id=task_id,
        file_path=str(target),
        user_id=user_id,
    )
    state["file_type"] = file_type
    resume_task_store.set(task_id, state)
    return state


async def analyze_resume_task(task_id: str) -> WorkflowState:
    """按需运行异步 Agent 1，并持久化每次状态更新。"""
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)
    if state.get("structured_resume"):
        return state
    return await run_resume_analysis_agent(
        state,
        on_state_update=resume_task_store.update,
        use_configured_llm=settings.AI_ANALYSIS_ENABLED,
    )
