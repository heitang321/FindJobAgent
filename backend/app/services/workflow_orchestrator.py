"""三 Agent 流程并行编排（LangGraph 版）。

重构前用 ThreadPoolExecutor + deepcopy 把 sync 的 A1 和 A2 前缀并行起来，
因为 sync_playwright 和 sync LLM 不能放进 asyncio 事件循环。

重构后 A1 / A2 / Playwright / LLM 全部 async，直接走 LangGraph 的
StateGraph 并发图（见 app.workflow.build_workflow_graph）：
START → [resume_analysis ‖ job_analysis_prefix] → job_analysis_match → END

LangGraph 内部用 asyncio.gather 并发执行 fan-out 分支，state diff 合并
由 LangGraph 的 channel-based reducer 自动完成，不再需要手动 deepcopy
和字段合并。

仍保留对「state 已有 structured_resume」场景的向后兼容：跳过 A1 直接
跑 A2 全流程（4 步），用于用户先轮询 A1 完成再提交 JD URL 的旧前端流程。
"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.agent.job_analysis_agent import JobAnalysisAgent
from app.schemas.workflow_state import WorkflowState
from app.workflow import build_workflow_graph

StateCallback = Callable[[WorkflowState], None]


async def arun_parallel_until_match(
    state: WorkflowState,
    jd_url: str,
    on_state_update: StateCallback | None = None,
) -> WorkflowState:
    """跑 LangGraph 并发图（A1‖A2前缀 → A2.4）。

    Args:
        state: WorkflowState，必须含 file_path；
               可不含 structured_resume（编排函数会启动 A1 补齐）
        jd_url: 招聘职位详情页 URL
        on_state_update: state 变更回调（如 ResumeTaskStore.update）

    Returns:
        更新后的 state，含 structured_resume / jd_raw_text /
        job_requirements / match_result / gap_report
    """
    start = time.time()

    # 写入 jd_url 给 job_analysis_prefix_node 读
    state["jd_url"] = jd_url
    state["current_stage"] = "job_analysis"
    state["error"] = None
    if on_state_update:
        on_state_update(state)

    skip_a1 = bool(state.get("structured_resume"))  # 已有则跳过 A1（重复调用场景）

    if skip_a1:
        # 向后兼容：state 已有 structured_resume，跳过 A1 直接跑 A2 全流程
        # 不走 LangGraph 图（图会强制跑 A1），直接调 JobAnalysisAgent.run
        agent = JobAnalysisAgent(on_state_update=on_state_update)
        state = await agent.run(state, jd_url)
    else:
        # 走 LangGraph 并发图：A1 ‖ A2 前缀 → A2.4
        graph = build_workflow_graph(on_state_update=on_state_update)
        state = await graph.ainvoke(state)

    if on_state_update:
        on_state_update(state)

    elapsed = time.time() - start
    print(f"[orchestrator] LangGraph A1‖A2前缀 + A2.4 总耗时: {elapsed:.1f}s")
    return state


# 保留旧函数名作为 sync 别名，向后兼容（虽然内部是 async）。
# 调用方需要 `await run_parallel_until_match(...)`。
run_parallel_until_match = arun_parallel_until_match
