"""三 Agent 流程并行编排。

依赖关系分析（确定无环）：
- A1 的 structured_resume 只被 A2 的 Tool 2.4 (matcher) 消费
- A2 的 Tool 2.1（抓 JD）/ 2.2（提取正文）/ 2.3（LLM 结构化 JD）
  完全不依赖 A1 的任何输出，只需 jd_url

所以 A1 全流程 可以和 A2 的前 3 步并行执行，最后串行跑 A2.4。

并行化收益：临界路径从 `A1 + A2前缀 + A2.4` 变成
`max(A1, A2前缀) + A2.4`，省下较短者的全部时间（通常省 8-15s）。

实现要点（避免常见坑）：
1. 不能用 asyncio.gather —— A1 用 sync LLM、A2.1 用 sync Playwright，
   sync API 在 asyncio 事件循环里会冲突报错
2. 用 ThreadPoolExecutor 把两个 sync 任务放到不同线程跑
3. 两个子任务用 deepcopy 的 state 副本，避免并发修改同一 dict
4. 子任务期间不调 on_state_update（避免中间状态污染 store），
   合并到主 state 后再统一调一次
5. 合并安全：A1 写 structured_resume/resume_evaluation，
   A2 前缀写 jd_raw_text/jd_source_type/job_requirements，字段不重叠
"""
from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from app.agent.job_analysis_agent import JobAnalysisAgent
from app.agent.resume_analysis_agent import run_resume_analysis_agent
from app.schema.workflow_state import WorkflowState

StateCallback = Callable[[WorkflowState], None]


def _run_a1(state: WorkflowState, on_state_update: StateCallback | None) -> WorkflowState:
    """Task A：A1 全流程（结构化简历）。

    内部走 file_type_detector → pdf_to_word_converter →
    document_text_extractor → resume_structurer（1 次 LLM）。
    """
    return run_resume_analysis_agent(
        state,
        on_state_update=on_state_update,
        use_configured_llm=True,
    )


def _run_a2_prefix(
    state: WorkflowState,
    jd_url: str,
    on_state_update: StateCallback | None,
) -> WorkflowState:
    """Task B：A2 的 Tool 2.1+2.2+2.3（抓 JD + 提取正文 + LLM 结构化 JD）。

    内部走 fetch_jd_from_url（CDP）→ extract_jd_text →
    extract_requirements（1 次 LLM）。完全不依赖 A1。
    """
    agent = JobAnalysisAgent(on_state_update=on_state_update)
    return agent.prepare_jd(state, jd_url)


def run_parallel_until_match(
    state: WorkflowState,
    jd_url: str,
    on_state_update: StateCallback | None = None,
) -> WorkflowState:
    """并行跑 A1 与 A2 前 3 步，两者完成后串行跑 A2.4 (matcher)。

    Args:
        state: WorkflowState，必须含 file_path；
               可不含 structured_resume（编排函数会启动 A1 补齐）
        jd_url: 招聘职位详情页 URL
        on_state_update: state 变更回调（必须线程安全，如 ResumeTaskStore.update）

    Returns:
        更新后的 state，含 structured_resume / jd_raw_text /
        job_requirements / match_result / gap_report
    """
    start = time.time()

    # 深拷贝两份副本给 A1 和 A2 前缀，避免并发修改同一 dict。
    # 子任务不调 on_state_update（传 None），避免中间状态污染 store。
    state_a1 = copy.deepcopy(state)
    state_a2 = copy.deepcopy(state)

    skip_a1 = bool(state.get("structured_resume"))  # 已有则跳过 A1（重复调用场景）

    with ThreadPoolExecutor(max_workers=2) as ex:
        future_a2 = ex.submit(_run_a2_prefix, state_a2, jd_url, None)
        future_a1 = None if skip_a1 else ex.submit(_run_a1, state_a1, None)

        state_a2_result = future_a2.result()
        state_a1_result = future_a1.result() if future_a1 else state_a1

    # ===== 合并子任务产出到主 state =====
    # A1 产出（A1 失败不阻塞 A2 前缀合并，但会标记 error 不再跑 matcher）
    if not skip_a1:
        state["structured_resume"] = state_a1_result.get("structured_resume", {})
        state["resume_evaluation"] = state_a1_result.get("resume_evaluation", {})
        if state_a1_result.get("error"):
            state["error"] = f"A1 failed: {state_a1_result['error']}"
            state["current_stage"] = "error"
            if on_state_update:
                on_state_update(state)
            return state

    # A2 前缀产出
    state["jd_raw_text"] = state_a2_result.get("jd_raw_text", "")
    state["jd_source_type"] = state_a2_result.get("jd_source_type", "url")
    state["job_requirements"] = state_a2_result.get("job_requirements", {})
    if state_a2_result.get("error"):
        state["error"] = f"A2 prefix failed: {state_a2_result['error']}"
        state["current_stage"] = "error"
        if on_state_update:
            on_state_update(state)
        return state

    # 两者都成功：写一次合并后的 state 到 store，再串行跑 matcher
    state["current_stage"] = "job_analysis"
    state["error"] = None
    if on_state_update:
        on_state_update(state)

    matcher_agent = JobAnalysisAgent(on_state_update=on_state_update)
    state = matcher_agent.match_resume(state)

    elapsed = time.time() - start
    print(f"[orchestrator] A1‖A2前缀 + A2.4 总耗时: {elapsed:.1f}s")
    return state
