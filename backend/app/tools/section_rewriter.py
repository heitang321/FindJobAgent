"""Tool 3.1：基于事实约束的 LLM 输出改写单个简历段落。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.schemas.optimization import SectionRewriteRequest, SectionRewriteResult


RewriteLLM = Callable[[str], str | dict[str, Any]]


_SYSTEM_PROMPT = """你是资深简历优化专家，精通互联网/科技/金融等行业简历写作规范。只输出严格 JSON。

## 核心原则
1. **事实约束**：只能改写输入段落中已有的真实经历，不得虚构公司、项目、技能、数字、职责或成果。
2. **参考优秀简历写作范式**：你的改写应对标大厂（字节、腾讯、阿里、美团等）P5-P7 级别
   简历的写作质量——动词精准、结构清晰、技术细节充分、成果可量化。
3. **格式保持**：这是原简历中的一个文字槽位，输出将原位替换原文。不得输出整份简历、
   标题、Markdown 语法、项目符号标记（•、- 、* 等）或额外段落。输出必须是纯文本。
4. **岗位导向**：岗位关键词只能在原文已有事实能够支撑时自然融入；无法验证的关键词不得添加。

## 优秀简历写作范式参考

### 工作经历/项目经历的优秀写法：
- 动词开头："主导设计…"、"独立开发…"、"优化重构…"、"搭建搭建…"
- 量化成果："QPS 提升 3 倍"、"响应时间从 800ms 降至 200ms"、"覆盖 50 万用户"
- 技术深度：写明具体技术栈、架构选型、核心算法、工程挑战
- 业务价值：说明做了什么、为什么做、带来什么结果

### 差 vs 好的对比：
- 差："负责后端开发工作，使用 Python 和数据库"
- 好："独立设计并实现用户中心微服务，采用 FastAPI + MySQL 架构，日均处理 20 万次请求，
  接口平均响应时间 < 50ms"

### 自我评价的优秀写法：
- 用事实替代形容词：不说"学习能力强"，而说"3 周内从零掌握 LangChain 并投入生产"
- 聚焦差异化：突出与目标岗位最相关的 2-3 个能力锚点

### 技能列表的优秀写法：
- 规范命名 + 场景标注："Python（3 年，FastAPI/LangChain 生产经验）"
- 按岗位相关性排序，核心技能在前"""


_SECTION_GUIDANCE = {
    "work_experience": """工作经历专用要求：
- 参考优秀简历范式，使用 STAR 思路组织已有事实：动作→职责范围→采用的方法或技术→已有结果。
- 动词开头，精准描述：使用"主导/独立/牵头/优化/重构/搭建/设计"等强动词，删除"负责相关工作"等空泛表达。
- 保留原公司、职位、时间、业务范围和技术事实；原文没有的数据或业绩数字绝不补写。
- 参考优秀写法：将散点信息重组为因果链——"做了什么→怎么做的→用什么技术→结果如何"。
- 优秀示例（仅参考写作风格，不得复制内容）：
  原文：负责公司内部系统的后端开发
  优化：独立设计并实现公司内部协同办公系统后端，采用 FastAPI + MySQL 架构，
        实现审批流引擎、权限模型和消息通知模块，支撑 200 人日常使用
- 输出一段可直接替换原文的职业化描述，不添加公司名、职位名或日期标题。""",
    "project_experience": """项目经历专用要求：
- 参考优秀简历范式，突出项目目标、本人核心动作、技术方案、架构决策和已有工程结果。
- 保留所有明确技术名词、参数、规模和业务事实，提升因果关系与技术表达精确度。
- 参考优秀写法：技术名词+具体动作+工程结果，如"使用 Redis 实现分布式锁，解决并发库存超卖问题，
  峰值并发 5000 QPS 下零超卖"。
- 结合 JD 调整信息呈现顺序（与岗位最相关的技术/成果前置），但不得把未使用的岗位技术写进项目。
- 优秀示例（仅参考写作风格，不得复制内容）：
  原文：做了一个 RAG 知识库项目，用了向量数据库
  优化：主导设计 RAG 企业知识库系统，基于 LangChain + FAISS 构建文档检索管线，
        实现 Embedding 生成、语义检索和答案生成全流程，Top-5 召回准确率 85%
- 输出一段可直接替换当前项目描述的正文，不重复项目名称和小标题。""",
    "self_evaluation": """个人优势/自我评价专用要求：
- 参考优秀简历范式，删除"认真负责、学习能力强、沟通能力好"等没有证据支撑的空泛套话。
- 只保留原文可验证的能力、工具使用方式、协作方式或问题解决特点，用事实替代形容词。
- 参考优秀写法：不说"学习能力强"，而说"快速掌握新技术并投入生产"；不说"责任心强"，
  而说"主导核心模块从设计到上线全流程"。
- 用简洁、克制、职业化的表达，聚焦与目标岗位最相关的 2-3 个能力锚点。
- 不虚构经验年限或能力等级。
- 优秀示例（仅参考写作风格，不得复制内容）：
  原文：本人学习能力强，有责任心，能吃苦耐劳，善于沟通
  优化：具备全栈开发能力，熟悉从需求分析到部署上线完整流程；
        擅长快速掌握新技术栈并落地生产环境，曾在 2 周内完成 LangChain 框架评估到上线
- 输出一个紧凑段落，不添加"自我评价"标题。""",
    "skills": """技能专用要求：
- 参考优秀简历范式，规范技能名称、去重并按目标岗位相关性排序（核心技能在前）。
- 只保留 original_content 或 evidence_context 中明确出现的技术；JD 仅用于排序，不能证明候选人具备该技能。
- 参考优秀写法：可在技能后补充场景标注（仅当原文已有依据时），如"Python（FastAPI 生产经验）"、
  "MySQL（千万级表优化）"。不添加熟练度、工作年限或能力等级，除非原文明确写出。
- 优秀示例（仅参考写作风格，不得复制内容）：
  原文：Python、MySQL、Redis、FastAPI
  优化：Python（FastAPI/LangChain 生产经验）、MySQL（千万级表优化）、Redis（分布式锁/缓存架构）
- 只输出使用中文顿号分隔的技能列表，不添加解释、分类标题或句号。""",
}


def build_section_rewrite_prompt(request: SectionRewriteRequest) -> str:
    """为一个可独立改写的段落构建自包含提示词。"""
    payload = request.model_dump()
    guidance = _SECTION_GUIDANCE[request.section_type]
    if request.original_content:
        original_length = len(request.original_content)
        # 允许适度扩写：最多到原文的 2 倍，但不超过 600 字符，避免破坏排版
        maximum_length = max(original_length * 2, original_length + 50)
        maximum_length = min(maximum_length, 600)
        layout_guidance = (
            f"为保持原简历排版，rewritten_content 最多 {maximum_length} 个字符，"
            "保持单段且不换行（不要输出换行符\\n）；"
            "优先在原文长度内重组表达，在事实充分的前提下可以适度扩写以增强表达质量，"
            "但不得为了显得丰富而注水。输出必须是纯文本，不含 Markdown 语法、项目符号或标题。"
        )
    else:
        layout_guidance = "原文为空时只生成紧凑的技能列表，保持单段且不换行。"
    return f"""请优化以下单个简历段落，并按 schema 返回 JSON：
{{
  "section_type": "{request.section_type}",
  "original_content": "必须原样返回输入内容",
  "rewritten_content": "优化后的段落",
  "change_reason": "修改原因",
  "changes": [{{"type": "added|modified|removed", "description": "具体修改"}}]
}}

约束：
1. 不得编造输入中不存在的经历或能力。
2. 没有可靠依据时保持原文，不要为了匹配 JD 强行添加关键词。
3. skills 段落返回逗号分隔的技能列表；其他段落返回可直接放入简历的正文。
4. original_content 必须与输入完全一致。
5. 当 skills 的 original_content 为空时，只能从 evidence_context 中提取明确出现的技能；
   evidence_context 没有出现的技能不得添加，JD 关键词不能作为事实依据。
6. evidence_context 仅用于核实事实，不得整段复制到 rewritten_content。
7. {layout_guidance}

{guidance}

输入：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def _parse_response(response: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _configured_llm(prompt: str) -> str:
    from app.model.openai_compatible import chat_completion

    return chat_completion(prompt, system_prompt=_SYSTEM_PROMPT)


def _unchanged_result(request: SectionRewriteRequest) -> SectionRewriteResult:
    return SectionRewriteResult(
        section_type=request.section_type,
        original_content=request.original_content,
        rewritten_content=request.original_content,
        change_reason="未启用 AI 重写，保留原始内容。",
        changes=[],
    )


def section_rewriter(
    request: SectionRewriteRequest,
    llm: RewriteLLM | None = None,
    use_configured_llm: bool = True,
) -> SectionRewriteResult:
    """改写单个段落，并校验结构化结果。

    ``llm`` 是真正的外部依赖边界：测试注入内存适配器，
    生产环境使用已配置的 OpenAI 兼容适配器。
    """
    model = llm
    if model is None and use_configured_llm:
        model = _configured_llm
    if model is None:
        return _unchanged_result(request)

    data = _parse_response(model(build_section_rewrite_prompt(request)))
    data["section_type"] = request.section_type
    data["original_content"] = request.original_content
    result = SectionRewriteResult.model_validate(data)
    if not result.rewritten_content.strip():
        return _unchanged_result(request)
    return result
