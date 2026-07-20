"""Job analysis endpoint with parallel orchestration.

前端提交 JD URL 后，调 LangGraph 并发图：A1（结构化简历）‖ A2 前 3 步
（抓 JD + 提取正文 + 结构化 JD），等两者完成串行跑 Tool 2.4（matcher）。

重构前用 ThreadPoolExecutor + sync def 路由绕开 asyncio 循环（因为 sync
Playwright 冲突）。重构后所有底层（LLM / Playwright / Agent.run）都改 async，
路由改回 async def，直接 await LangGraph 的 ainvoke()，FastAPI 原生 async 路由
不再需要线程池。

含 2 次 LLM 调用 + 1 次 CDP 抓取，整体耗时约 20-45s（优化前 30-60s），
前端 axios timeout 仍需 >= 120s。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.job import JobAnalysisRequest, JobAnalysisResponse
from app.services.resume_tasks import resume_task_store
from app.services.workflow_orchestrator import arun_parallel_until_match

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
async def analyze_job(task_id: str, payload: JobAnalysisRequest) -> JobAnalysisResponse:
    """异步路由函数：调 LangGraph 并发图（A1‖A2前缀 → A2.4）。

    - 若 state.structured_resume 已有：跳过 A1，只跑 A2 全流程（4 步）
    - 若 state.structured_resume 为空：走 LangGraph 图，
      A1 和 A2 前 3 步并发执行（asyncio.gather），两者完成后串行跑 A2.4
    """
    state = _task_or_404(task_id)

    # 不再做"必须 A1 已完成"的前置检查 —— 编排函数会按需启动 A1
    try:
        updated = await arun_parallel_until_match(
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
