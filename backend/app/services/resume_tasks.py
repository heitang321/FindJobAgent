"""Agent 1 简历分析使用的内存任务服务。"""

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
        """合并更新任务状态。

        LangGraph 并发分支可能只发布自己负责的字段。使用字段级合并可以避免
        A1/A2 的 partial state 覆盖另一分支已经写入的结果。
        """
        task_id = state["task_id"]
        with self._lock:
            current = dict(self._tasks.get(task_id, {}))
            current.update(state)
            self._tasks[task_id] = current


resume_task_store = ResumeTaskStore()


def _safe_filename(filename: str) -> str:
    name = Path(filename or "resume").name
    return name.replace("/", "_").replace("\\", "_")


class ResumeUploadTooLarge(ValueError):
    """上传文件超过配置上限。"""


def save_uploaded_resume(file: UploadFile, user_id: str) -> WorkflowState:
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
        with target.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.RESUME_MAX_UPLOAD_BYTES:
                    raise ResumeUploadTooLarge(
                        f"简历文件不能超过 {settings.RESUME_MAX_UPLOAD_BYTES // 1024 // 1024} MB"
                    )
                out.write(chunk)

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
    """运行 Agent 1 并把每次 state 变更回写到 store。

    重构后是 async：resume_structurer 内部走 ChatOpenAI.ainvoke()，
    BackgroundTasks.add_task 原生支持 async 函数（FastAPI 自动放进 event loop）。
    """
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
