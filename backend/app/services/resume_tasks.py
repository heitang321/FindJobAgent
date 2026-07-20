"""Agent 1 简历分析使用的内存任务服务。"""
from __future__ import annotations

import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import UploadFile

from app.agent.resume_analysis_agent import run_resume_analysis_agent
from app.schema.workflow_state import WorkflowState, initial_workflow_state
from app.tools.file_type_detector import file_type_detector
from app.core.config import settings


class ResumeTaskStore:
    """轻量级进程内任务存储。

    后续可以替换为数据库任务表，而不需要改变 API 表面。
    WorkflowState 的结构已经与这种替换方式兼容。
    """

    def __init__(self):
        self._tasks: dict[str, WorkflowState] = {}
        self._lock = Lock()

    def set(self, task_id: str, state: WorkflowState) -> None:
        with self._lock:
            self._tasks[task_id] = dict(state)  # 状态替换只需要浅拷贝

    def get(self, task_id: str) -> WorkflowState | None:
        with self._lock:
            state = self._tasks.get(task_id)
            return dict(state) if state else None

    def update(self, state: WorkflowState) -> None:
        self.set(state["task_id"], state)


resume_task_store = ResumeTaskStore()


def _safe_filename(filename: str) -> str:
    name = Path(filename or "resume").name
    return name.replace("/", "_").replace("\\", "_")


def save_uploaded_resume(file: UploadFile) -> WorkflowState:
    task_id = uuid4().hex
    upload_dir = Path(settings.RESUME_UPLOAD_DIR) / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    target = upload_dir / _safe_filename(file.filename or "resume")
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    state = initial_workflow_state(task_id=task_id, file_path=str(target))
    state["file_type"] = file_type_detector(str(target))["file_type"]
    resume_task_store.set(task_id, state)
    return state


def analyze_resume_task(task_id: str) -> WorkflowState:
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)
    return run_resume_analysis_agent(
        state,
        on_state_update=resume_task_store.update,
        use_configured_llm=settings.AI_ANALYSIS_ENABLED,
    )
