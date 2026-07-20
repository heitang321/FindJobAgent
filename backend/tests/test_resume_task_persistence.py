"""WorkflowState 与 MySQL ORM 映射的合并回归测试。"""

from app.models.resume_task import ResumeTask
from app.schemas.workflow_state import initial_workflow_state
from app.services.resume_tasks import _orm_to_state, _state_to_orm


def test_task_mapping_preserves_owner_and_job_search_state():
    state = initial_workflow_state(
        task_id="mapping-task",
        file_path="resume.docx",
        user_id="owner-123",
    )
    state["jd_url"] = "https://jobs.zhaopin.com/example"
    state["job_search_results"] = [
        {
            "title": "Python 工程师",
            "url": "https://jobs.zhaopin.com/example",
        }
    ]
    state["selected_jd_url"] = "https://jobs.zhaopin.com/example"

    task = ResumeTask(task_id=state["task_id"])
    _state_to_orm(state, task)
    restored = _orm_to_state(task)

    assert restored["user_id"] == "owner-123"
    assert restored["jd_url"] == state["jd_url"]
    assert restored["job_search_results"] == state["job_search_results"]
    assert restored["selected_jd_url"] == state["selected_jd_url"]


def test_partial_state_can_clear_previous_error():
    task = ResumeTask(task_id="partial-task", error="previous failure")

    _state_to_orm({"task_id": "partial-task", "error": None}, task)

    assert task.error is None
