"""岗位接口的输入安全与自动推荐回归测试。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.job import _derive_keywords_from_resume
from app.api.v1.router import api_router
from app.api.deps import get_current_user
from app.schemas.job import JobAnalysisRequest
from app.schemas.workflow_state import initial_workflow_state
from app.services.resume_tasks import resume_task_store


def _client() -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test-user",
        "email": "test@example.com",
        "username": "tester",
    }
    app.include_router(api_router, prefix="/api/v1")
    return TestClient(app)


def test_job_url_rejects_non_recruitment_hosts():
    with pytest.raises(ValidationError):
        JobAnalysisRequest(jd_url="http://127.0.0.1:8000/internal")


def test_job_url_accepts_zhaopin_subdomains():
    payload = JobAnalysisRequest(
        jd_url="https://jobs.zhaopin.com/CC123456789J00000000000.htm"
    )
    assert payload.jd_url.startswith("https://jobs.zhaopin.com/")


def test_derive_keywords_extracts_compact_technical_terms():
    structured_resume = {
        "basic_info": {},
        "skills": [
            "熟练使用 ChatGPT、Claude Code 等 AI 工具辅助开发",
            "掌握 RAG（检索增强生成）架构设计与实现",
            "熟悉 FAISS 向量数据库与 sentence-transformers 文本嵌入",
        ],
    }

    keywords = _derive_keywords_from_resume(structured_resume)

    assert keywords == "RAG FAISS"
    assert len(keywords) <= 80


def test_search_retries_with_broader_automatic_keywords(monkeypatch, tmp_path: Path):
    from app.tools.jd_fetcher import NoSearchResultsError

    task_id = "fallback-search-task"
    state = initial_workflow_state(
        task_id,
        str(tmp_path / "resume.docx"),
        user_id="test-user",
    )
    state["structured_resume"] = {
        "basic_info": {},
        "skills": ["RAG", "FAISS", "sentence-transformers"],
        "project_experience": [],
    }
    resume_task_store.set(task_id, state)
    attempted: list[str] = []

    async def fake_fetch_search_page(**kwargs):
        attempted.append(kwargs["keywords"])
        if kwargs["keywords"] == "RAG FAISS":
            raise NoSearchResultsError("精确搜索无结果")
        return [
            {
                "title": "大模型应用工程师",
                "url": "https://jobs.zhaopin.com/CC123J000002.htm",
                "salary": "20-30K",
                "skills": ["RAG"],
                "location": "上海",
                "experience": "3-5年",
                "education": "本科",
                "company": "示例公司",
                "company_tags": ["人工智能"],
            }
        ]

    monkeypatch.setattr(
        "app.tools.jd_fetcher.fetch_search_page", fake_fetch_search_page
    )

    response = _client().post(
        f"/api/v1/job/{task_id}/search",
        json={"keywords": None, "city": "", "max_results": 10},
    )

    assert response.status_code == 200
    assert attempted == ["RAG FAISS", "RAG"]
    assert response.json()["keywords"] == "RAG"
    assert response.json()["job_search_results"][0]["title"] == "大模型应用工程师"


def test_search_lazily_analyzes_resume(monkeypatch, tmp_path: Path):
    task_id = "lazy-search-task"
    state = initial_workflow_state(
        task_id,
        str(tmp_path / "resume.docx"),
        user_id="test-user",
    )
    resume_task_store.set(task_id, state)

    async def fake_analyze_resume(requested_task_id: str):
        assert requested_task_id == task_id
        current = resume_task_store.get(task_id)
        current["structured_resume"] = {
            "basic_info": {"job_intent": "Python 后端工程师"},
            "skills": ["Python", "FastAPI", "LangGraph"],
            "project_experience": [],
        }
        current["current_stage"] = "done"
        resume_task_store.update(current)
        return current

    async def fake_fetch_search_page(**kwargs):
        assert "Python 后端工程师" in kwargs["keywords"]
        return [
            {
                "title": "Python 后端工程师",
                "url": "https://jobs.zhaopin.com/CC123J000001.htm",
                "salary": "15-25K",
                "skills": ["Python", "FastAPI"],
                "location": "上海",
                "experience": "3-5年",
                "education": "本科",
                "company": "示例公司",
                "company_tags": ["互联网"],
            }
        ]

    monkeypatch.setattr("app.api.v1.job.analyze_resume_task", fake_analyze_resume)
    monkeypatch.setattr(
        "app.tools.jd_fetcher.fetch_search_page", fake_fetch_search_page
    )

    response = _client().post(
        f"/api/v1/job/{task_id}/search",
        json={"keywords": None, "city": "", "max_results": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_search_results"][0]["title"] == "Python 后端工程师"
    assert resume_task_store.get(task_id)["job_search_results"]
