"""Agent 1: 简历分析 Agent。

内部是「确定性工具链 + 一次 LLM 调用」的组合，不是每步都需要 LLM。

执行顺序是线性的：1.1 → 1.2（如需）→ 1.3 → 1.4。

- Tool 1.1 file_type_detector — 检测文件类型（纯函数）
- Tool 1.2 pdf_to_word_converter — PDF 转 Word（确定性操作，仅在 PDF 时触发）
- Tool 1.3 document_text_extractor — 提取文本（确定性操作）
- Tool 1.4 resume_structurer — 结构化提取 + 评估（唯一调用 LLM 的步骤）

Tool 之间不直接传数据，而是读写 WorkflowState 的字段。每个 node 是一个
LangGraph 节点函数，接收 state、读取上游字段、写入自己的产出字段。
"""
from __future__ import annotations

from collections.abc import Callable


from app.schema.workflow_state import WorkflowState
from app.tools.document_text_extractor import document_text_extractor
from app.tools.file_type_detector import file_type_detector
from app.tools.pdf_to_word_converter import pdf_to_word_converter
from app.tools.resume_structurer import LLMCallable, resume_structurer

# State 变更回调类型，services 层可用它异步写入数据库
StateCallback = Callable[[WorkflowState], None]


# ===== LangGraph 节点函数 =====


def detect_file_type_node(state: WorkflowState) -> WorkflowState:
    """Tool 1.1: 检测文件类型，写入 state["file_type"]。"""
    result = file_type_detector(state["file_path"])
    state["file_type"] = result["file_type"]
    return state


def convert_pdf_node(state: WorkflowState) -> WorkflowState:
    """Tool 1.2: PDF 转 Word，写入 state["converted_file_path"]。

    - PDF：调用 pdf_to_word_converter 转换
    - DOCX：直接跳过，converted_file_path = 原路径
    - 其他：converted_file_path = None
    """
    file_type = state.get("file_type", "unknown")
    if file_type == "pdf":
        result = pdf_to_word_converter(state["file_path"])
        state["converted_file_path"] = (
            str(result["converted_path"]) if result.get("success") else None
        )
    elif file_type == "docx":
        state["converted_file_path"] = state["file_path"]
    else:
        state["converted_file_path"] = None
    return state


def extract_text_node(state: WorkflowState) -> WorkflowState:
    """Tool 1.3: 提取文本，写入 state["raw_text"]。

    PDF 必须直接读取原文件，避免保真 Word 中的页面图片无法提取文本，
    也避免可编辑格式转换造成的文本重排。DOCX 使用原始/转换后的 Word。
    """
    if state.get("file_type") == "pdf":
        extract_path = state["file_path"]
    else:
        extract_path = state.get("converted_file_path") or state["file_path"]
    result = document_text_extractor(extract_path)
    state["raw_text"] = str(result["raw_text"])
    return state


def structure_resume_node(
    state: WorkflowState,
    llm: LLMCallable | None = None,
    use_configured_llm: bool = True,
) -> WorkflowState:
    """Tool 1.4: 结构化提取 + 评估，写入 state["structured_resume"] 和 state["resume_evaluation"]。

    这是 Agent 内部唯一调用 LLM 的步骤。
    """
    result = resume_structurer(
        state.get("raw_text", ""),
        llm=llm,
        use_configured_llm=use_configured_llm and llm is None,
    )
    state["structured_resume"] = result["structured_resume"]
    state["resume_evaluation"] = result["evaluation"]
    return state


# ===== Agent 运行器 =====


class ResumeAnalysisAgent:
    """简历分析 Agent（Agent 1）。

    线性执行四个 Tool 节点，通过 WorkflowState 传递数据。
    支持注入 LLM callable 和 state 变更回调（用于 services 层持久化）。
    """

    def __init__(
        self,
        llm: LLMCallable | None = None,
        on_state_update: StateCallback | None = None,
        use_configured_llm: bool = True,
    ):
        self.llm = llm
        self.on_state_update = on_state_update
        self.use_configured_llm = use_configured_llm

    def _publish(self, state: WorkflowState) -> None:
        """通过回调通知 services 层持久化 state。"""
        if self.on_state_update:
            self.on_state_update(state)

    def run(self, state: WorkflowState) -> WorkflowState:
        """执行完整的简历分析流程：1.1 → 1.2 → 1.3 → 1.4。"""
        try:
            state["current_stage"] = "analyzing"
            state["error"] = None
            self._publish(state)

            # Tool 1.1: 检测文件类型
            detect_file_type_node(state)
            self._publish(state)

            file_type = state.get("file_type", "unknown")
            if file_type not in {"pdf", "docx", "doc"}:
                raise ValueError(f"Unsupported resume file type: {file_type}")
            if file_type == "doc":
                raise ValueError(
                    "Legacy .doc files are detected but not supported for text extraction yet."
                )

            # Tool 1.2: PDF 转 Word（如需）
            convert_pdf_node(state)
            self._publish(state)

            if state.get("file_type") == "pdf" and not state.get("converted_file_path"):
                raise ValueError("PDF to DOCX conversion failed.")

            # Tool 1.3: 提取文本
            extract_text_node(state)
            self._publish(state)

            # Tool 1.4: 结构化提取 + 评估（唯一 LLM 调用）
            structure_resume_node(
                state,
                llm=self.llm,
                use_configured_llm=self.use_configured_llm,
            )
            self._publish(state)

            state["current_stage"] = "done"
            self._publish(state)
            return state

        except Exception as exc:
            state["current_stage"] = "error"
            state["error"] = str(exc)
            self._publish(state)
            return state


def run_resume_analysis_agent(
    state: WorkflowState,
    llm: LLMCallable | None = None,
    on_state_update: StateCallback | None = None,
    use_configured_llm: bool = True,
) -> WorkflowState:
    """便捷函数：创建 ResumeAnalysisAgent 并运行。

    供 services 层和测试使用。
    """
    return ResumeAnalysisAgent(
        llm=llm,
        on_state_update=on_state_update,
        use_configured_llm=use_configured_llm,
    ).run(state)
