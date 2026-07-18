"""Agent 2: 岗位分析 Agent。

和 Agent 1 同样的模式：线性工具链 + LLM 调用，通过 WorkflowState 传递数据。

执行顺序：
- Tool 2.1 jd_fetcher — 从 URL 抓取 JD 页面文本（CDP 连接真实 Edge）
- Tool 2.2 jd_extractor — 从页面文本提取 JD 正文（文本标记提取）
- Tool 2.3 requirement_extractor — LLM 结构化 JD（function calling）
- Tool 2.4 matcher — LLM 简历-岗位匹配 + gap 分析

Tool 2.1 和 2.2 是确定性操作，2.3 和 2.4 调用 LLM。
Agent 1 产出的 structured_resume 在 Tool 2.4 被消费。
"""
from __future__ import annotations

from collections.abc import Callable

from app.schemas.workflow_state import WorkflowState
from app.tools.jd_extractor import extract_jd_text
from app.tools.jd_fetcher import fetch_jd_from_url
from app.tools.matcher import analyze_match, split_to_workflow_fields
from app.tools.requirement_extractor import extract_requirements

# State 变更回调类型，services 层可用它异步写入数据库
StateCallback = Callable[[WorkflowState], None]


# ===== LangGraph 节点函数 =====


def fetch_jd_node(state: WorkflowState, jd_url: str) -> WorkflowState:
    """Tool 2.1: 从 URL 抓取 JD 页面文本，写入 state["jd_raw_text"]。

    使用 CDP 连接真实 Edge 浏览器，绕过 EdgeOne 机器人检测。
    前置条件：已通过 login 脚本登录招聘网站。
    """
    page_text = fetch_jd_from_url(jd_url)
    state["jd_raw_text"] = page_text
    state["jd_source_type"] = "url"
    return state


def extract_jd_node(state: WorkflowState) -> WorkflowState:
    """Tool 2.2: 从页面文本提取 JD 正文，覆写 state["jd_raw_text"]。

    用文本标记（"职位描述"→"工作地点"）定位 JD 边界，
    去除导航栏、相似职位、公司介绍等噪音，压缩约 80%。
    """
    page_text = state.get("jd_raw_text", "")
    jd_text = extract_jd_text(page_text)
    state["jd_raw_text"] = jd_text
    return state


def structure_jd_node(state: WorkflowState) -> WorkflowState:
    """Tool 2.3: LLM 结构化 JD，写入 state["job_requirements"]。

    将 JD 正文转为 JobRequirement 结构化对象（职位名、薪资、技能、
    岗位职责、任职要求），通过 with_structured_output + function calling
    约束输出格式。
    """
    jd_text = state.get("jd_raw_text", "")
    job_req = extract_requirements(jd_text)
    state["job_requirements"] = job_req.model_dump()
    return state


def match_resume_node(state: WorkflowState) -> WorkflowState:
    """Tool 2.4: LLM 简历-岗位匹配，写入 state["match_result"] 和 state["gap_report"]。

    消费 Agent 1 产出的 structured_resume 和节点 2.3 的 job_requirements，
    用 LLM 做语义级匹配，产出匹配度和 gap 分析。
    """
    structured_resume = state.get("structured_resume", {})
    job_req_dict = state.get("job_requirements", {})

    # 从 dict 重建 JobRequirement 对象（matcher 需要 Pydantic 模型）
    from app.tools.requirement_extractor import JobRequirement
    job_req = JobRequirement(**job_req_dict)

    analysis = analyze_match(structured_resume, job_req)
    match_result, gap_report = split_to_workflow_fields(analysis)
    state["match_result"] = match_result
    state["gap_report"] = gap_report
    return state


# ===== Agent 运行器 =====


class JobAnalysisAgent:
    """岗位分析 Agent（Agent 2）。

    线性执行四个 Tool 节点，通过 WorkflowState 传递数据。
    Agent 1 的 structured_resume 在 Tool 2.4 被消费。

    用法::

        agent = JobAnalysisAgent(on_state_update=persist_fn)
        state = initial_workflow_state(task_id, file_path)
        # ... Agent 1 先运行，填充 structured_resume ...
        state = agent.run(state, jd_url="https://www.zhaopin.com/jobdetail/...")
    """

    def __init__(self, on_state_update: StateCallback | None = None):
        self.on_state_update = on_state_update

    def _publish(self, state: WorkflowState) -> None:
        """通过回调通知 services 层持久化 state。"""
        if self.on_state_update:
            self.on_state_update(state)

    def run(self, state: WorkflowState, jd_url: str) -> WorkflowState:
        """执行完整的岗位分析流程：2.1 → 2.2 → 2.3 → 2.4。

        Args:
            state: WorkflowState，必须包含 Agent 1 产出的 structured_resume
            jd_url: 招聘职位详情页 URL

        Returns:
            更新后的 WorkflowState，包含 jd_raw_text, job_requirements,
            match_result, gap_report
        """
        try:
            state["current_stage"] = "job_analysis"
            state["error"] = None
            self._publish(state)

            # Tool 2.1: 从 URL 抓取 JD 页面
            fetch_jd_node(state, jd_url)
            self._publish(state)

            # Tool 2.2: 提取 JD 正文（去噪）
            extract_jd_node(state)
            self._publish(state)

            # Tool 2.3: LLM 结构化 JD
            structure_jd_node(state)
            self._publish(state)

            # Tool 2.4: LLM 简历-岗位匹配
            match_resume_node(state)
            self._publish(state)

            state["current_stage"] = "done"
            self._publish(state)
            return state

        except Exception as exc:
            state["current_stage"] = "error"
            state["error"] = str(exc)
            self._publish(state)
            return state


def run_job_analysis_agent(
    state: WorkflowState,
    jd_url: str,
    on_state_update: StateCallback | None = None,
) -> WorkflowState:
    """便捷函数：创建 JobAnalysisAgent 并运行。

    供 services 层和测试使用。
    """
    return JobAnalysisAgent(on_state_update=on_state_update).run(state, jd_url)
