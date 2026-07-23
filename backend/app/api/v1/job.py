"""Job analysis endpoint with parallel orchestration.

Frontend submits JD URL after, calls LangGraph concurrent graph: A1（structured resume）‖ A2 first 3 steps
（grab JD + extract text + structure JD），waits for both to complete and then runs Tool 2.4（matcher）.

Routing and LLM/Agent calls use native async. Playwright's full synchronous lifecycle is separately placed
in a worker thread to avoid Uvicorn event loop unable to create browser driver subprocess on Windows.

Contains 2 LLM calls + 1 CDP fetch, overall time is about 20-45s (before optimization 30-60s),
frontend axios timeout still needs to be >= 120s.
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
from app.core.redis_client import (
    get_cached_jd_analysis,
    get_cached_search,
    set_cached_jd_analysis,
    set_cached_search,
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
    """From resume structured_resume derive search keywords.

    Prioritize job intent, then extract up to 3 short tech words from skill descriptions. LLM sometimes puts
    an entire skill description in a list; directly concatenating would generate a super long, low-hit job board query.
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

    # First collect recognizable tech identifiers (Python, RAG, FAISS, C++ etc.).
    for skill in skills:
        for token in _TECH_TOKEN_RE.findall(str(skill)):
            if token.casefold() not in _GENERIC_SEARCH_TOKENS:
                add(token)
        if len(parts) == _MAX_AUTO_SEARCH_TERMS:
            break

    # Pure Chinese and itself short skills can still be keywords; full description sentences are skipped.
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
    """Generate search terms from precise to broad, keep order and deduplicate."""
    terms = list(dict.fromkeys(keywords.split()))
    candidates = [keywords]
    if len(terms) > 1:
        candidates.append(terms[0])
    return list(dict.fromkeys(candidates))


def _filter_and_pagate(
    cards: list[dict],
    state: dict,
    task_id: str,
    keywords: str,
    payload: JobSearchRequest,
) -> JobSearchResponse:
    """Filter and paginate the fetched job list, return JobSearchResponse."""
    filtered = list(cards)

    # Debug: log filter params
    print(
        f"[filter] input={len(cards)} cards "
        f"city={payload.filter_city!r} exp={payload.filter_experience!r} "
        f"edu={payload.filter_education!r} kw={payload.filter_keyword!r} "
        f"page={payload.page} size={payload.page_size}",
        flush=True,
    )

    # City filter (backend filtering)
    fc = (payload.filter_city or "").strip()
    if fc:
        filtered = [
            c for c in filtered if fc in (c.get("location") or "")
        ]

    # Experience requirement filter
    fx = (payload.filter_experience or "").strip()
    if fx:
        filtered = [
            c for c in filtered if fx in (c.get("experience") or "")
        ]

    # Education requirement filter
    fe = (payload.filter_education or "").strip()
    if fe:
        filtered = [
            c for c in filtered if fe in (c.get("education") or "")
        ]

    # Keyword fuzzy search (job title/company name/skills)
    fk = (payload.filter_keyword or "").strip().lower()
    if fk:
        def _match(c: dict) -> bool:
            title = (c.get("title") or "").lower()
            company = (c.get("company") or "").lower()
            skills = c.get("skills") or []
            skills_text = " ".join(str(s) for s in skills).lower()
            return fk in title or fk in company or fk in skills_text

        filtered = [c for c in filtered if _match(c)]

    total = len(filtered)
    page = payload.page
    page_size = payload.page_size
    total_pages = max(1, (total + page_size - 1) // page_size)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_cards = filtered[start_idx:end_idx]

    return JobSearchResponse(
        task_id=task_id,
        current_stage=state.get("current_stage", "job_input"),
        error=None,
        keywords=keywords,
        job_search_results=[JobCardItem(**card) for card in page_cards],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/{task_id}/analyze",
    response_model=JobAnalysisResponse,
    summary="Submit JD URL and run A1 and A2 first 3 steps in parallel, then run matcher in series",
)
async def analyze_job(
    task_id: str,
    payload: JobAnalysisRequest,
    user: CurrentUser,
) -> JobAnalysisResponse:
    """Asynchronous route function: call LangGraph concurrent graph (A1‖A2 prefix → A2.4).

    - If state.structured_resume already exists: skip A1, only run A2 full flow (4 steps)
    - If state.structured_resume is empty: follow LangGraph graph,
      A1 and A2 first 3 steps run in parallel (asyncio.gather), then run A2.4 after both complete
    """
    state = _task_or_404(task_id, user["id"])

    # ===== Redis cache: return in seconds for same JD URL =====
    cached = get_cached_jd_analysis(payload.jd_url)
    if cached:
        # Merge cache result into state
        for k in ("jd_raw_text", "job_requirements", "match_result", "gap_report"):
            if k in cached:
                state[k] = cached[k]
        state["selected_jd_url"] = payload.jd_url
        state["current_stage"] = "job_analysis_done"
        resume_task_store.update(state)
        print(f"[job.analyze] JD cache hit url={payload.jd_url[:60]}", flush=True)
        return JobAnalysisResponse(
            task_id=task_id,
            current_stage="job_analysis_done",
            error=None,
            jd_raw_text=cached.get("jd_raw_text", ""),
            job_requirements=cached.get("job_requirements") or {},
            match_result=cached.get("match_result") or {},
            gap_report=cached.get("gap_report") or {},
        )

    # No longer do "must A1 completed" pre-check —— orchestrator function will start A1 as needed
    try:
        updated = await arun_parallel_until_match(
            state,
            jd_url=payload.jd_url,
            on_state_update=resume_task_store.update,
        )
    except Exception as exc:
        # Orchestrator function already try/except wrote error, here catch any uncaptured exceptions
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

    # Cache JD analysis result (exclude state internal fields, only cache analysis data)
    set_cached_jd_analysis(
        payload.jd_url,
        {
            "jd_raw_text": updated.get("jd_raw_text", ""),
            "job_requirements": updated.get("job_requirements") or {},
            "match_result": updated.get("match_result") or {},
            "gap_report": updated.get("gap_report") or {},
        },
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


@router.post(
    "/{task_id}/search",
    response_model=JobSearchResponse,
    summary="Automatically search zhaopin jobs based on resume content, return card list for user selection",
)
async def search_jobs(
    task_id: str,
    payload: JobSearchRequest,
    user: CurrentUser,
) -> JobSearchResponse:
    """Automatically derive keywords from resume structured_resume, call zhaopin search page fetch job cards.

    Process:
        1. From state["structured_resume"] take skills derive search keywords (or use payload.keywords)
        2. Call fetch_search_page fetch search page + parse cards
        3. Write into state["job_search_results"], persist to resume_task_store
        4. Return JobSearchResponse (with card list)

    If structured_resume is empty, this endpoint will first execute A1 as needed, then continue job search.
    This way upload phase does not need to pre-call LLM, manual JD flow can still keep A1/A2 parallel.
    """
    state = _task_or_404(task_id, user["id"])

    search_city = payload.city or ""
    has_explicit_kw = bool(payload.keywords and payload.keywords.strip())
    has_filters = bool(
        payload.filter_city
        or payload.filter_experience
        or payload.filter_education
        or payload.filter_keyword
    )

    # ===== Filter/pagination: reuse existing results, do not refetch =====
    # When keywords are empty (auto-derived) and existing search results exist:
    #   - City unchanged → directly filter+paginate existing results (second-level return)
    #   - City changed → refetch
    existing_cards = state.get("job_search_results") or []
    last_city = state.get("last_search_city", "")
    last_kw = state.get("last_search_keywords", "")
    if (
        not has_explicit_kw
        and existing_cards
        and search_city == last_city
    ):
        print(
            f"[job.search] reuse existing results filter/pagination "
            f"total={len(existing_cards)} page={payload.page} "
            f"filters={has_filters}",
            flush=True,
        )
        return _filter_and_pagate(
            existing_cards, state, task_id, last_kw, payload
        )

    # ===== Redis cache: job search results =====
    if has_explicit_kw:
        check_kw = payload.keywords.strip()
        cached_search = get_cached_search(check_kw, search_city)
        if cached_search is not None:
            state["job_search_results"] = cached_search
            state["last_search_keywords"] = check_kw
            state["last_search_city"] = search_city
            resume_task_store.update(state)
            print(
                f"[job.search] Redis cache hit keywords={check_kw!r} city={search_city!r}",
                flush=True,
            )
            return _filter_and_pagate(
                cached_search, state, task_id, check_kw, payload
            )

    # Derive search keywords
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
                    detail=f"Resume structuring failed: {state.get('error') or 'No structured result generated'}",
                )
            structured = state["structured_resume"]
        keywords = _derive_keywords_from_resume(structured)

    print(
        f"[job.search] task_id={task_id} keywords={keywords!r} city={payload.city!r}",
        flush=True,
    )

    # Auto-recommend allows falling back from multiple tech words to core word, avoid normal zero result being misreported as fetch failure.
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
            detail=f"Job search failed ({type(exc).__name__}): {error_detail}",
        ) from exc

    # Cache search results
    set_cached_search(keywords, search_city, cards_raw)

    # Write back state, persist
    state["job_search_results"] = cards_raw
    state["last_search_keywords"] = keywords
    state["last_search_city"] = search_city
    state["selected_jd_url"] = ""  # Clear previous selection
    resume_task_store.update(state)

    print(
        f"[job.search] task_id={task_id} wrote {len(cards_raw)} job cards", flush=True
    )

    return _filter_and_pagate(cards_raw, state, task_id, keywords, payload)
