"""LangGraph 工作流编排。

重构后 API 和 CLI 共用此图，真正用 LangGraph 的并发节点编排
「A1（简历分析）‖ A2 前 3 步（抓 JD + 提取正文 + 结构化 JD）→ A2.4（matcher）」。

图结构::

    START
      ├──> resume_analysis        (Agent 1 全流程，写 structured_resume)
      │               \\
      │                \\
      ├──> job_analysis_prefix    (Agent 2 前 3 步，写 jd_raw_text / job_requirements)
      │                //
      │               //
      └──> job_analysis_match     (Agent 2 第 4 步，等 A1 和 A2 前缀都完成才跑)
                            │
                            ▼
                           END

LangGraph 的 StateGraph 对同一个 START 加多条 edge 实现并发 fan-out，
对同一个下游节点连多条上游 edge 实现 barrier（等所有上游完成才跑）。
节点函数都是 async def，配合 ChatOpenAI.ainvoke() 和 async_playwright。

Agent 3（简历优化）目前仍由 BackgroundTasks 独立触发，不在本图内。
"""

from __future__ import annotations

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from app.agent.job_analysis_agent import JobAnalysisAgent
from app.agent.resume_analysis_agent import ResumeAnalysisAgent
from app.schemas.workflow_state import WorkflowState, initial_workflow_state

StateCallback = Callable[[WorkflowState], None]


def build_workflow_graph(on_state_update: StateCallback | None = None):
    """构建并编译 LangGraph 工作流图。

    Args:
        on_state_update: 可选的 state 变更回调（如 ResumeTaskStore.update）。
            并发节点只发布自己负责的字段 patch，避免完整分支副本互相覆盖。
            传 None 时节点不会发回调（CLI 模式典型用法）。

    Returns:
        编译后的 LangGraph Runnable，可用 `await app.ainvoke(state)` 运行。
        每次 build 都会重新 compile，开销可忽略（不含 LLM 调用）。
    """
    # ===== LangGraph 节点函数 =====
    # 每个节点调用 agent.run(state_copy)，然后只 return 自己写入的字段（partial state）。
    # 为什么不能 return 完整 state：A1 和 A2 前缀并发执行时，两个分支都会返回
    # 继承自初始 state 的字段（file_path / file_type / raw_text 等），LangGraph
    # 默认 reducer 看到两个分支都写这些字段会报
    # "Can receive only one value per step"。只返回自己写的字段（partial state）后，
    # 字段不重叠，LangGraph 合并安全。共享字段 current_stage / error 走 Annotated reducer。
    # 注：传给 agent 的是 dict(state) 拷贝，避免 agent 原地修改输入 state 后我们无法
    # 通过 diff 提取自己写入的字段。

    A1_FIELDS = (
        "current_stage",
        "error",
        "file_type",
        "converted_file_path",
        "raw_text",
        "structured_resume",
        "resume_evaluation",
    )
    A2_PREFIX_FIELDS = (
        "current_stage",
        "error",
        "jd_source_type",
        "jd_raw_text",
        "job_requirements",
    )
    A2_MATCH_FIELDS = ("current_stage", "error", "match_result", "gap_report")

    async def resume_analysis_node(state: WorkflowState) -> dict:
        """Agent 1: 简历分析（全流程）。

        走 file_type_detector → pdf_to_word_converter →
        document_text_extractor → resume_structurer（1 次 LLM ainvoke）。
        写入 structured_resume / resume_evaluation。
        """
        import time

        t0 = time.time()
        print(
            f"[langgraph] A1 resume_analysis_node 开始, task_id={state.get('task_id')}",
            flush=True,
        )
        agent = ResumeAnalysisAgent(
            use_configured_llm=True,
            # 并发分支不能发布继承自初始状态的完整副本，否则会覆盖另一分支。
            on_state_update=None,
        )
        result = await agent.run(dict(state))
        print(
            f"[langgraph] A1 resume_analysis_node 完成, 耗时={time.time()-t0:.1f}s",
            flush=True,
        )
        partial = {k: result.get(k) for k in A1_FIELDS if k in result}
        if on_state_update:
            on_state_update(
                {
                    "task_id": state["task_id"],
                    **{
                        k: v
                        for k, v in partial.items()
                        if k not in {"current_stage", "error"}
                    },
                }
            )
        return partial

    async def job_analysis_prefix_node(state: WorkflowState) -> dict:
        """Agent 2 前 3 步：抓 JD + 提取正文 + LLM 结构化 JD。

        完全不依赖 A1 的 structured_resume，只依赖 state["jd_url"]，
        因此 LangGraph 会把它和 resume_analysis_node 并发执行。
        写入 jd_raw_text / jd_source_type / job_requirements。
        """
        import time

        t0 = time.time()
        print(
            f"[langgraph] A2_prefix job_analysis_prefix_node 开始, task_id={state.get('task_id')}",
            flush=True,
        )
        jd_url = state.get("jd_url", "")
        if not jd_url:
            return {"current_stage": "error", "error": "jd_url 未设置"}
        agent = JobAnalysisAgent(on_state_update=None)
        result = await agent.prepare_jd(dict(state), jd_url)
        print(
            f"[langgraph] A2_prefix job_analysis_prefix_node 完成, 耗时={time.time()-t0:.1f}s",
            flush=True,
        )
        partial = {k: result.get(k) for k in A2_PREFIX_FIELDS if k in result}
        if on_state_update:
            on_state_update(
                {
                    "task_id": state["task_id"],
                    **{
                        k: v
                        for k, v in partial.items()
                        if k not in {"current_stage", "error"}
                    },
                }
            )
        return partial

    async def job_analysis_match_node(state: WorkflowState) -> dict:
        """Agent 2 第 4 步：matcher（LLM 简历-岗位匹配 + gap 分析）。

        前置条件（由 LangGraph barrier 保证）：
            - state["structured_resume"] 已由 resume_analysis_node 写入
            - state["job_requirements"] 已由 job_analysis_prefix_node 写入
        写入 match_result / gap_report。
        """
        import time

        t0 = time.time()
        print(
            f"[langgraph] A2_match job_analysis_match_node 开始, task_id={state.get('task_id')}",
            flush=True,
        )
        agent = JobAnalysisAgent(on_state_update=None)
        result = await agent.match_resume(dict(state))
        print(
            f"[langgraph] A2_match job_analysis_match_node 完成, 耗时={time.time()-t0:.1f}s",
            flush=True,
        )
        partial = {k: result.get(k) for k in A2_MATCH_FIELDS if k in result}
        if on_state_update:
            on_state_update({"task_id": state["task_id"], **partial})
        return partial

    # ===== 图构建 =====
    graph = StateGraph(WorkflowState)

    graph.add_node("resume_analysis", resume_analysis_node)
    graph.add_node("job_analysis_prefix", job_analysis_prefix_node)
    graph.add_node("job_analysis_match", job_analysis_match_node)

    # 并发 fan-out：START 同时指向 A1 和 A2 前缀
    # LangGraph 对同一 source 加多条 edge 即并发执行下游节点。
    graph.add_edge(START, "resume_analysis")
    graph.add_edge(START, "job_analysis_prefix")

    # barrier：A1 和 A2 前缀都完成才跑 matcher
    # LangGraph 对同一 target 加多条上游 edge 即等待所有上游完成。
    graph.add_edge("resume_analysis", "job_analysis_match")
    graph.add_edge("job_analysis_prefix", "job_analysis_match")

    graph.add_edge("job_analysis_match", END)

    # Agent 3 预留（目前仍走 BackgroundTasks，未集成进图）:
    # graph.add_node("resume_optimization", optimization_node)
    # graph.add_edge("job_analysis_match", "resume_optimization")
    # graph.add_edge("resume_optimization", END)

    return graph.compile()


async def run_workflow(
    task_id: str,
    file_path: str,
    jd_url: str,
) -> WorkflowState:
    """运行完整的简历优化工作流（A1‖A2前缀 → A2.4）。

    Args:
        task_id: 任务唯一标识
        file_path: 简历文件路径（PDF 或 DOCX）
        jd_url: 招聘职位详情页 URL

    Returns:
        最终的 WorkflowState，包含结构化简历、JD分析、匹配结果和gap报告
    """
    # 初始化状态
    state = initial_workflow_state(task_id=task_id, file_path=file_path)
    state["jd_url"] = jd_url

    # 构建并运行图（CLI 模式不发 on_state_update 回调）
    app = build_workflow_graph(on_state_update=None)
    result = await app.ainvoke(state)
    return result


if __name__ == "__main__":
    import asyncio
    import sys

    async def _cli() -> None:
        if len(sys.argv) < 3:
            print("用法: python -m app.workflow <简历文件路径> <JD URL>")
            sys.exit(1)

        resume_path = sys.argv[1]
        jd_url = sys.argv[2]

        print(f"简历: {resume_path}")
        print(f"JD URL: {jd_url}")
        print("启动 LangGraph 工作流（A1‖A2前缀 → A2.4 并发）...\n")

        result = await run_workflow(
            task_id="cli-001",
            file_path=resume_path,
            jd_url=jd_url,
        )

        print(f"\n{'=' * 60}")
        print(f"stage: {result['current_stage']}")
        if result.get("error"):
            print(f"error: {result['error']}")
        else:
            job = result.get("job_requirements", {})
            match = result.get("match_result", {})
            gap = result.get("gap_report", {})
            print(f"职位: {job.get('title', '?')}")
            print(f"匹配度: {match.get('overall_score', '?')}/100")
            print(f"已匹配技能: {match.get('matched_skills', [])}")
            print(f"缺失技能: {match.get('missing_skills', [])}")
            print(f"关键差距: {len(gap.get('critical_gaps', []))}条")
            print(f"改进建议: {len(gap.get('improvement_suggestions', []))}条")

    asyncio.run(_cli())
