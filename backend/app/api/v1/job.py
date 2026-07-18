"""Agent 2 job analysis endpoint.

前端提交 JD URL 后，同步执行 Agent 2（fetch JD → extract → structure → match）。
跑完写入 state 后返回 job_requirements、match_result、gap_report。

由于 Agent 2 含 2 次 LLM 调用（结构化 JD + 匹配分析）和一次 CDP 抓取，
整体耗时约 30-60s，前端 axios timeout 需调长（>= 120s）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.agent.job_analysis_agent import run_job_analysis_agent
from app.schemas.job import JobAnalysisRequest, JobAnalysisResponse
from app.services.resume_tasks import resume_task_store

router = APIRouter()


def _task_or_404(task_id: str) -> dict:
    state = resume_task_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job analysis task not found")
    return state


@router.post(
    "/{task_id}/analyze",
    response_model=JobAnalysisResponse,
    summary="提交 JD URL 同步执行岗位分析（Agent 2）",
)
def analyze_job(task_id: str, payload: JobAnalysisRequest) -> JobAnalysisResponse:
    """同步路由函数（非 async）：FastAPI 会自动放到线程池运行，
    避开 asyncio 事件循环与 Playwright sync API 的冲突。"""
    state = _task_or_404(task_id)

    # 前置条件：Agent 1 必须已产出 structured_resume
    if not state.get("structured_resume"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume analysis must finish before job analysis.",
        )

    # 同步执行 Agent 2，错误按严格快速失败策略直接 500
    try:
        updated = run_job_analysis_agent(
            state,
            jd_url=payload.jd_url,
            on_state_update=resume_task_store.update,
        )
    except Exception as exc:
        # run_job_analysis_agent 内部已 try/except 写 error，这里兜底未捕获异常
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job analysis failed: {exc}",
        ) from exc

    if updated.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job analysis failed: {updated['error']}",
        )

    return JobAnalysisResponse(
        task_id=task_id,
        current_stage=updated.get("current_stage", "done"),
        error=updated.get("error"),
        jd_raw_text=updated.get("jd_raw_text", ""),
        job_requirements=updated.get("job_requirements") or {},
        match_result=updated.get("match_result") or {},
        gap_report=updated.get("gap_report") or {},
    )
