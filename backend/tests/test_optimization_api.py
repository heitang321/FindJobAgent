"""Agent 3 FastAPI 接口测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1.router import api_router  # noqa: E402
from app.api.deps import get_current_user  # noqa: E402
from app.schemas.workflow_state import initial_workflow_state  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.resume_tasks import resume_task_store  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-user",
        "email": "test@example.com",
        "username": "tester",
    }
    app.include_router(api_router, prefix="/api/v1")
    return TestClient(app)


def _ready_state(task_id: str) -> dict:
    state = initial_workflow_state(task_id, "resume.docx", user_id="test-user")
    state["structured_resume"] = {
        "basic_info": {"name": "李四", "phone": "", "email": "", "location": ""},
        "education": [],
        "work_experience": [],
        "project_experience": [],
        "skills": ["Python"],
        "self_evaluation": "认真负责",
    }
    state["job_requirements"] = {"title": "Python 工程师", "skills": ["Python"]}
    state["gap_report"] = {
        "sections": [{"section_type": "self_evaluation", "status": "weak"}]
    }
    return state


class TestOptimizationApi:
    def setup_method(self):
        resume_task_store._tasks.clear()
        settings.AI_ANALYSIS_ENABLED = False

    def test_trigger_result_and_download(self, tmp_path):
        settings.OPTIMIZATION_OUTPUT_DIR = str(tmp_path)
        state = _ready_state("task-ready")
        resume_task_store.set(state["task_id"], state)
        client = _client()

        trigger = client.post("/api/v1/optimize/task-ready")

        assert trigger.status_code == 202
        assert trigger.json()["current_stage"] == "optimizing"

        result = client.get("/api/v1/optimize/task-ready/result")
        assert result.status_code == 200
        assert result.json()["current_stage"] == "done"
        assert result.json()["download_ready"] is True
        assert "sections" in result.json()["diff_report"]

        download = client.get("/api/v1/optimize/task-ready/download")
        assert download.status_code == 200
        assert download.content.startswith(b"PK")
        assert (
            "officedocument.wordprocessingml.document"
            in download.headers["content-type"]
        )

    def test_trigger_requires_previous_agents(self):
        state = initial_workflow_state(
            "task-incomplete",
            "resume.docx",
            user_id="test-user",
        )
        resume_task_store.set(state["task_id"], state)

        response = _client().post("/api/v1/optimize/task-incomplete")

        assert response.status_code == 409

    def test_trigger_requires_match_or_gap_result(self):
        state = _ready_state("task-without-match-result")
        state["match_result"] = {}
        state["gap_report"] = {}
        resume_task_store.set(state["task_id"], state)

        response = _client().post("/api/v1/optimize/task-without-match-result")

        assert response.status_code == 409
        assert "match result" in response.json()["detail"].casefold()

    def test_missing_task_returns_404(self):
        response = _client().get("/api/v1/optimize/missing/result")
        assert response.status_code == 404

    def test_download_before_completion_returns_409(self):
        state = _ready_state("task-not-ready")
        resume_task_store.set(state["task_id"], state)

        response = _client().get("/api/v1/optimize/task-not-ready/download")

        assert response.status_code == 409
