"""LangGraph 工作流编排。

将 Agent 1（简历分析）和 Agent 2（岗位分析）串联成线性 StateGraph。
Agent 3（简历优化）由独立触发接口在岗位匹配完成后执行。

图结构::

    START → resume_analysis → job_analysis → END
                                        (→ optimizing 预留)

每个节点是一个 Agent 的 run 方法，通过 WorkflowState 传递数据。
LangGraph 会自动管理状态合并和节点调度。
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.job_analysis_agent import JobAnalysisAgent
from app.agent.resume_analysis_agent import ResumeAnalysisAgent
from app.schemas.workflow_state import WorkflowState, initial_workflow_state


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

    # 添加边：线性流程
    graph.add_edge(START, "resume_analysis")
    graph.add_edge("resume_analysis", "job_analysis")
    graph.add_edge("job_analysis", END)

    # Agent 3 预留（实现后取消注释）:
    # graph.add_node("resume_optimization", optimization_node)
    # graph.add_edge("job_analysis", "resume_optimization")
    # graph.add_edge("resume_optimization", END)

    return graph.compile()


# ===== 便捷运行函数 =====


def run_workflow(
    task_id: str,
    file_path: str,
    jd_url: str,
) -> WorkflowState:
    """运行完整的简历优化工作流。

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

    # 构建并运行图
    app = build_workflow_graph()
    result = app.invoke(state)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("用法: python -m app.workflow <简历文件路径> <JD URL>")
        sys.exit(1)

    resume_path = sys.argv[1]
    jd_url = sys.argv[2]

    print(f"简历: {resume_path}")
    print(f"JD URL: {jd_url}")
    print("启动工作流...\n")

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
        print(f"职位: {job.get('title', '?')}")
        print(f"匹配度: {match.get('overall_score', '?')}/100")
        print(f"已匹配技能: {match.get('matched_skills', [])}")
        print(f"缺失技能: {match.get('missing_skills', [])}")
        print(f"关键差距: {len(gap.get('critical_gaps', []))}条")
        print(f"改进建议: {len(gap.get('improvement_suggestions', []))}条")
