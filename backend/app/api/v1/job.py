"""Job analysis endpoint with parallel orchestration.

前端提交 JD URL 后，调 LangGraph 并发图：A1（结构化简历）‖ A2 前 3 步
（抓 JD + 提取正文 + 结构化 JD），等两者完成串行跑 Tool 2.4（matcher）。

路由和 LLM/Agent 调用使用原生 async。Playwright 的完整同步生命周期单独放在
工作线程中，避免 Windows 下 Uvicorn 事件循环无法创建浏览器驱动子进程。

含 2 次 LLM 调用 + 1 次 CDP 抓取，整体耗时约 20-45s（优化前 30-60s），
前端 axios timeout 仍需 >= 120s。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser
from app.schemas.job import (
    JobAnalysisRequest,
    JobAnalysisResponse,
    JobCardItem,
    JobSearchRequest,
    JobSearchResponse,
)
from app.services.resume_tasks import analyze_resume_task, resume_task_store
from app.services.workflow_orchestrator import arun_parallel_until_match

router = APIRouter()

_TECH_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*(?:-[A-Za-z0-9+#.]+)*")
_GENERIC_SEARCH_TOKENS = {
    "ai",
    "chatgpt",
    "claude",
    "code",
    "etc",
    "tool",
    "tools",
    "using",
}
_SKILL_PREFIX_RE = re.compile(r"^(熟练使用|熟练掌握|熟悉|掌握|精通|了解)")
_MAX_AUTO_SEARCH_TERMS = 2


def _task_or_404(task_id: str, user_id: str) -> dict:
    state = resume_task_store.get(task_id)
    if state is None or state.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Job analysis task not found")
    return state


def _derive_keywords_from_resume(structured_resume: dict) -> str:
    """从简历 structured_resume 推导搜索关键词。

    优先使用求职方向，再从技能描述中提取最多 3 个短技术词。LLM 有时会把一整句
    技能描述放进列表；直接拼接会生成超长、低命中的招聘站查询。
    """
    skills = structured_resume.get("skills", []) or []
    basic = structured_resume.get("basic_info", {}) or {}
    job_intent = basic.get("job_intent") or basic.get("intended_position") or ""

    parts: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        value = " ".join(candidate.strip().split())
        key = value.casefold()
        if value and key not in seen and len(parts) < _MAX_AUTO_SEARCH_TERMS:
            parts.append(value)
            seen.add(key)

    intent = " ".join(str(job_intent).split())
    if intent:
        if len(intent) <= 30:
            add(intent)
        else:
            for token in _TECH_TOKEN_RE.findall(intent):
                if token.casefold() not in _GENERIC_SEARCH_TOKENS:
                    add(token)

    # 先收集可识别的技术标识（Python、RAG、FAISS、C++ 等）。
    for skill in skills:
        for token in _TECH_TOKEN_RE.findall(str(skill)):
            if token.casefold() not in _GENERIC_SEARCH_TOKENS:
                add(token)
        if len(parts) == _MAX_AUTO_SEARCH_TERMS:
            break

    # 纯中文且本身简短的技能仍然可以作为关键词；完整描述句则跳过。
    if len(parts) < _MAX_AUTO_SEARCH_TERMS:
        for skill in skills:
            concise = _SKILL_PREFIX_RE.sub("", " ".join(str(skill).split())).strip(
                "：:，,。；; "
            )
            if 1 < len(concise) <= 16 and not _TECH_TOKEN_RE.search(concise):
                add(concise)
            if len(parts) == _MAX_AUTO_SEARCH_TERMS:
                break

    if not parts:
        projects = structured_resume.get("project_experience", []) or []
        for p in projects[:2]:
            name = p.get("name", "") if isinstance(p, dict) else ""
            if name:
                add(str(name)[:30])
    if not parts:
        return "Python 后端"

    keywords = " ".join(parts)
    if len(keywords) <= 80:
        return keywords
    return keywords[:80].rsplit(" ", 1)[0] or keywords[:80]


def _search_keyword_candidates(keywords: str) -> list[str]:
    """生成从精确到宽泛的搜索词，保持顺序并去重。"""
    terms = list(dict.fromkeys(keywords.split()))
    candidates = [keywords]
    if len(terms) > 1:
        candidates.append(terms[0])
    return list(dict.fromkeys(candidates))


@router.post(
    "/{task_id}/analyze",
    response_model=JobAnalysisResponse,
    summary="提交 JD URL 并行执行 A1 与 A2 前 3 步，最后串行跑 matcher",
)
async def analyze_job(
    task_id: str,
    payload: JobAnalysisRequest,
    user: CurrentUser,
) -> JobAnalysisResponse:
    """异步路由函数：调 LangGraph 并发图（A1‖A2前缀 → A2.4）。

    - 若 state.structured_resume 已有：跳过 A1，只跑 A2 全流程（4 步）
    - 若 state.structured_resume 为空：走 LangGraph 图，
      A1 和 A2 前 3 步并发执行（asyncio.gather），两者完成后串行跑 A2.4
    """
    state = _task_or_404(task_id, user["id"])

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

    updated["selected_jd_url"] = payload.jd_url
    resume_task_store.update(updated)

    return JobAnalysisResponse(
        task_id=task_id,
        current_stage=updated.get("current_stage", "done"),
        error=updated.get("error"),
        jd_raw_text=updated.get("jd_raw_text", ""),
        job_requirements=updated.get("job_requirements") or {},
        match_result=updated.get("match_result") or {},
        gap_report=updated.get("gap_report") or {},
    )


@router.post(
    "/{task_id}/search",
    response_model=JobSearchResponse,
    summary="根据简历内容自动检索 zhaopin 岗位，返回卡片列表供用户选择",
)
async def search_jobs(
    task_id: str,
    payload: JobSearchRequest,
    user: CurrentUser,
) -> JobSearchResponse:
    """根据简历 structured_resume 自动推导关键词，调 zhaopin 搜索页抓取岗位卡片。

    流程：
        1. 从 state["structured_resume"] 取 skills 推导搜索关键词（或用 payload.keywords）
        2. 调 fetch_search_page 抓搜索页 + 解析卡片
        3. 写入 state["job_search_results"]，持久化到 resume_task_store
        4. 返回 JobSearchResponse（含卡片列表）

    若 structured_resume 为空，本接口会先按需执行一次 A1，再继续岗位检索。
    这样上传阶段无需提前调用 LLM，手动 JD 流程仍可保持 A1/A2 并发。
    """
    state = _task_or_404(task_id, user["id"])

    # 推导搜索关键词
    automatic_keywords = not (payload.keywords and payload.keywords.strip())
    if not automatic_keywords:
        keywords = payload.keywords.strip()
    else:
        structured = state.get("structured_resume") or {}
        if not structured:
            state = await analyze_resume_task(task_id)
            if state.get("error") or not state.get("structured_resume"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"简历结构化失败：{state.get('error') or '未生成结构化结果'}",
                )
            structured = state["structured_resume"]
        keywords = _derive_keywords_from_resume(structured)

    print(
        f"[job.search] task_id={task_id} keywords={keywords!r} city={payload.city!r}",
        flush=True,
    )

    # 自动推荐允许从多个技术词退化到核心单词，避免正常零结果被误报为抓取失败。
    candidates = (
        _search_keyword_candidates(keywords) if automatic_keywords else [keywords]
    )
    cards_raw: list[dict] = []
    try:
        from app.tools.jd_fetcher import NoSearchResultsError, fetch_search_page

        for index, candidate in enumerate(candidates):
            try:
                cards_raw = await fetch_search_page(
                    keywords=candidate,
                    city=payload.city,
                    max_results=payload.max_results,
                )
                keywords = candidate
                break
            except NoSearchResultsError:
                keywords = candidate
                action = (
                    "trying fallback"
                    if index + 1 < len(candidates)
                    else "no broader fallback available"
                )
                print(
                    f"[job.search] no results for {candidate!r}, {action}",
                    flush=True,
                )
    except Exception as exc:
        error_detail = str(exc).strip() or type(exc).__name__
        print(
            f"[job.search] fetch_search_page failed "
            f"({type(exc).__name__}): {error_detail}",
            flush=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"岗位检索失败（{type(exc).__name__}）：{error_detail}",
        ) from exc

    # 写回 state，持久化
    state["job_search_results"] = cards_raw
    state["selected_jd_url"] = ""  # 清空之前的选择
    resume_task_store.update(state)

    print(
        f"[job.search] task_id={task_id} 写入 {len(cards_raw)} 个岗位卡片", flush=True
    )

    return JobSearchResponse(
        task_id=task_id,
        current_stage=state.get("current_stage", "job_input"),
        error=None,
        keywords=keywords,
        job_search_results=[JobCardItem(**card) for card in cards_raw],
    )
