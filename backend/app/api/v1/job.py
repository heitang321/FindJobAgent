"""Job analysis endpoint with parallel orchestration.

前端提交 JD URL 后，编排函数并行启动 Agent 1（结构化简历）和 Agent 2 的
前 3 步（抓 JD + 提取正文 + 结构化 JD），等两者完成后串行跑 Tool 2.4
（matcher）。临界路径从 A1+A2前缀+matcher 变成 max(A1, A2前缀)+matcher，
省 8-15s。

若 state.structured_resume 已存在（用户已轮询过 A1 完成再提交 JD），
编排函数自动跳过 A1 只跑 A2 全流程，向后兼容旧前端流程。

含 2 次 LLM 调用 + 1 次 CDP 抓取，整体耗时约 20-45s（优化前 30-60s），
前端 axios timeout 仍需 >= 120s。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.job import JobAnalysisRequest, JobAnalysisResponse
from app.services.resume_tasks import resume_task_store
from app.services.workflow_orchestrator import run_parallel_until_match

router = APIRouter()


def _task_or_404(task_id: str) -> dict:
    state = resume_task_store.get(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Job analysis task not found")
    return state


@router.post(
    "/{task_id}/analyze",
    response_model=JobAnalysisResponse,
    summary="提交 JD URL 并行执行 A1 与 A2 前 3 步，最后串行跑 matcher",
)
def analyze_job(task_id: str, payload: JobAnalysisRequest) -> JobAnalysisResponse:
    """同步路由函数（非 async）：FastAPI 会自动放到线程池运行，
    避开 asyncio 事件循环与 Playwright sync API 的冲突。

    内部调 run_parallel_until_match：
    - 若 state.structured_resume 已有：跳过 A1，只跑 A2 全流程（4 步）
    - 若 state.structured_resume 为空：并行跑 A1 和 A2 前 3 步，
      两者完成后串行跑 A2.4
    """
    state = _task_or_404(task_id)

    # 不再做"必须 A1 已完成"的前置检查 —— 编排函数会按需启动 A1
    try:
        updated = run_parallel_until_match(
            state,
            jd_url=payload.jd_url,
            on_state_update=resume_task_store.update,
        )
    except Exception as exc:
        # 编排函数内部已 try/except 写 error，这里兜底未捕获异常
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
