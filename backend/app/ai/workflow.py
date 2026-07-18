"""LangGraph 工作流编排。

将三个 Agent 串联成线性 StateGraph：
Agent 1（简历分析）→ Agent 2（岗位分析）→ Agent 3（简历优化）。

图结构::

    START → resume_analysis → job_analysis → resume_optimization → END

每个节点是一个 Agent 的 run 方法，通过 WorkflowState 传递数据。
LangGraph 会自动管理状态合并和节点调度。
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.ai.agent.job_analysis_agent import JobAnalysisAgent
from app.ai.agent.resume_analysis_agent import ResumeAnalysisAgent
from app.ai.agent.resume_optimization_agent import ResumeOptimizationAgent
from app.ai.schema.workflow_state import WorkflowState, initial_workflow_state


# ===== LangGraph 节点函数 =====


def resume_analysis_node(state: WorkflowState) -> WorkflowState:
    """Agent 1: 简历分析。

    读取 state["file_path"]，执行文件类型检测、PDF转换、文本提取、
    LLM结构化，写入 structured_resume 和 resume_evaluation。
    """
    agent = ResumeAnalysisAgent(use_configured_llm=True)
    return agent.run(state)


def job_analysis_node(state: WorkflowState) -> WorkflowState:
    """Agent 2: 岗位分析。

    读取 state["jd_url"] 和 state["structured_resume"]，
    执行 JD 抓取、正文提取、LLM结构化、简历匹配，
    写入 jd_raw_text, job_requirements, match_result, gap_report。
    """
    jd_url = state.get("jd_url", "")
    if not jd_url:
        state["current_stage"] = "error"
        state["error"] = "jd_url 未设置"
        return state
    agent = JobAnalysisAgent()
    return agent.run(state, jd_url=jd_url)


def resume_optimization_node(state: WorkflowState) -> WorkflowState:
    """Agent 3: 简历优化。

    读取 state["structured_resume"]、state["job_requirements"]、
    state["gap_report"]，执行 LLM 章节改写、diff 生成、DOCX 输出，
    写入 optimized_resume, diff_report, output_file_path, optimization_summary。
    """
    agent = ResumeOptimizationAgent(use_configured_llm=True)
    return agent.run(state)


# ===== 图构建 =====


def build_workflow_graph():
    """构建并编译 LangGraph 工作流图。

    Returns:
        编译后的 LangGraph Runnable，可用 .invoke(state) 运行
    """
    graph = StateGraph(WorkflowState)

    # 添加节点
    graph.add_node("resume_analysis", resume_analysis_node)
    graph.add_node("job_analysis", job_analysis_node)
    graph.add_node("resume_optimization", resume_optimization_node)

    # 添加边：线性流程 Agent 1 → Agent 2 → Agent 3
    graph.add_edge(START, "resume_analysis")
    graph.add_edge("resume_analysis", "job_analysis")
    graph.add_edge("job_analysis", "resume_optimization")
    graph.add_edge("resume_optimization", END)

    return graph.compile()


# ===== 便捷运行函数 =====


def run_workflow(
    task_id: str,
    file_path: str,
    jd_url: str,
    output_dir: str | None = None,
) -> WorkflowState:
    """运行完整的简历优化工作流（三个 Agent 全串联）。

    Args:
        task_id: 任务唯一标识
        file_path: 简历文件路径（PDF 或 DOCX）
        jd_url: 招聘职位详情页 URL
        output_dir: 优化后 DOCX 输出目录，None 则用默认配置

    Returns:
        最终的 WorkflowState，包含结构化简历、JD分析、匹配结果、
        gap报告、优化简历和 DOCX 输出路径
    """
    # 初始化状态
    state = initial_workflow_state(task_id=task_id, file_path=file_path)
    state["jd_url"] = jd_url

    # 构建并运行图
    app = build_workflow_graph()
    result = app.invoke(state)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("用法: python -m app.ai.workflow <简历文件路径> <JD URL>")
        sys.exit(1)

    resume_path = sys.argv[1]
    jd_url = sys.argv[2]

    print(f"简历: {resume_path}")
    print(f"JD URL: {jd_url}")
    print("启动工作流（Agent 1 → Agent 2 → Agent 3）...\n")

    result = run_workflow(
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
        summary = result.get("optimization_summary", {})
        print(f"职位: {job.get('title', '?')}")
        print(f"匹配度: {match.get('overall_score', '?')}/100")
        print(f"关键差距: {len(gap.get('critical_gaps', []))}条")
        print(f"改写章节: {summary.get('rewritten_sections', [])}")
        print(f"输出文件: {result.get('output_file_path', '无')}")
