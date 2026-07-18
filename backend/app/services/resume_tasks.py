"""In-memory task service for Agent 1 resume analysis."""
from __future__ import annotations

import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import UploadFile

from app.agent.resume_analysis_agent import run_resume_analysis_agent
from app.schemas.workflow_state import WorkflowState, initial_workflow_state
from app.tools.file_type_detector import file_type_detector
from app.core.config import settings


class ResumeTaskStore:
    """Small process-local store.

    This can be swapped for a database-backed task table without changing the
    API surface. The WorkflowState shape is already compatible with that.
    """

    def __init__(self):
        self._tasks: dict[str, WorkflowState] = {}
        self._lock = Lock()

    def set(self, task_id: str, state: WorkflowState) -> None:
        with self._lock:
            self._tasks[task_id] = dict(state)  # shallow copy is enough for state replacement

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
