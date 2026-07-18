"""简历-岗位匹配工具

将 Agent 1 产出的结构化简历与 Agent 2 节点3 产出的结构化 JD 进行对比，
用 LLM 分析匹配度和差距，产出 match_result 和 gap_report。

设计思路：
1. 定义 MatchAnalysis Pydantic 模型，包含匹配结果 + gap 分析
2. 把结构化简历和 JobRequirement 都转成 JSON 喂给 LLM
3. LLM 做语义级匹配（不只是关键词对比），能识别
   "做过 RAG 系统" 匹配 "RAG" 这种表达差异
4. 产出可直接用于 WorkflowState 的 match_result 和 gap_report

为什么用 LLM 做匹配而不是规则对比：
    规则对比只能做精确关键词匹配（"Python" == "Python"），
    但简历和 JD 的表达方式差异很大：
    - 简历写 "基于 LangChain 开发了多 Agent 系统"
    - JD 要求 "熟悉 LangGraph 或类似框架完成 Agent 编排"
    规则匹配会漏掉这种语义级匹配，LLM 能理解语义等价性。
"""
from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.model.model import MyModel
from app.tools.requirement_extractor import JobRequirement


class MatchAnalysis(BaseModel):
    """简历-岗位匹配分析结果

    同时包含匹配结果（match_result）和 gap 分析（gap_report），
    调用方可按需拆分成 WorkflowState 的两个字段。
    """
    # ===== 匹配结果 (match_result) =====
    overall_score: int = Field(
        description="整体匹配度评分 0-100，100表示完全匹配"
    )
    matched_skills: list[str] = Field(
        description="简历中已具备且岗位需要的技能，如['Python', 'LangChain', 'RAG']"
    )
    missing_skills: list[str] = Field(
        description="岗位需要但简历中缺失的技能，如['MCP', 'A2A']"
    )
    extra_skills: list[str] = Field(
        description="简历中额外具备但岗位未明确要求的技能（加分项），如['Docker', 'Redis']"
    )
    experience_match: str = Field(
        description="经验匹配分析，说明候选人经验是否满足岗位要求及原因"
    )
    education_match: str = Field(
        description="学历匹配分析，说明候选人学历是否满足岗位要求"
    )
    overall_assessment: str = Field(
        description="整体匹配评估，不少于100字，总结候选人与岗位的契合度"
    )

    # ===== Gap 分析 (gap_report) =====
    critical_gaps: list[str] = Field(
        description="关键差距列表，每条说明一个具体差距及其影响"
    )
    improvement_suggestions: list[str] = Field(
        description="针对此岗位的简历改进建议，每条具体可执行"
    )
    gap_summary: str = Field(
        description="差距分析总结，不少于80字，概括最需要弥补的差距和优先方向"
    )


_SYSTEM_PROMPT = """你是一位资深技术招聘顾问，擅长评估候选人与岗位的匹配度。

你的任务：对比结构化简历和结构化岗位需求（JD），输出匹配分析和差距报告。

分析原则：
1. 语义级匹配：不要只做关键词对比。"用 LangChain 开发过 Agent" 应匹配 "熟悉 LangGraph 或类似框架"。
2. 技能分类：matched_skills 是简历已有且岗位需要的；missing_skills 是岗位需要但简历没有的；
   extra_skills 是简历有但岗位没要求的（加分项）。
3. 经验评估：对比简历的工作年限/项目深度与岗位的经验要求，给出匹配判断。
4. 学历评估：对比简历学历与岗位学历要求。
5. Gap 分析：找出最关键的 2-5 个差距，给出具体可执行的改进建议。
6. 评分标准：90+ 高度匹配，70-89 基本匹配但有提升空间，50-69 部分匹配需较多补充，<50 匹配度低。
"""

_HUMAN_TEMPLATE = """请对比以下结构化简历和岗位需求，输出匹配分析。

【结构化简历】
{resume_json}

【岗位需求（JD）】
{job_json}

请输出匹配度评分、技能匹配（已匹配/缺失/额外）、经验匹配、学历匹配、
关键差距和改进建议。"""


def analyze_match(
    structured_resume: dict,
    job_requirement: JobRequirement,
) -> MatchAnalysis:
    """用 LLM 分析结构化简历与岗位需求的匹配度和差距。

    Args:
        structured_resume: Agent 1 (resume_structurer) 产出的结构化简历 dict，
            包含 basic_info, education, work_experience, project_experience,
            skills, self_evaluation 等字段
        job_requirement: Agent 2 节点3 (requirement_extractor) 产出的 JobRequirement

    Returns:
        MatchAnalysis: 包含匹配结果和 gap 分析的结构化对象，
            可通过 .model_dump() 转成 dict 写入 WorkflowState
    """
    model = MyModel.get_model()
    structured_model = model.with_structured_output(MatchAnalysis)

    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _HUMAN_TEMPLATE),
    ])

    chain = prompt | structured_model

    result = chain.invoke({
        "resume_json": json.dumps(structured_resume, ensure_ascii=False, indent=2),
        "job_json": job_requirement.model_dump_json(indent=2),
    })
    return result


def split_to_workflow_fields(
    analysis: MatchAnalysis,
) -> tuple[dict, dict]:
    """将 MatchAnalysis 拆分成 WorkflowState 需要的 match_result 和 gap_report。

    Returns:
        (match_result, gap_report) 两个 dict
    """
    data = analysis.model_dump()
    match_result = {
        "overall_score": data["overall_score"],
        "matched_skills": data["matched_skills"],
        "missing_skills": data["missing_skills"],
        "extra_skills": data["extra_skills"],
        "experience_match": data["experience_match"],
        "education_match": data["education_match"],
        "overall_assessment": data["overall_assessment"],
    }
    gap_report = {
        "critical_gaps": data["critical_gaps"],
        "improvement_suggestions": data["improvement_suggestions"],
        "gap_summary": data["gap_summary"],
    }
    return match_result, gap_report
