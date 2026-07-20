"""JD 结构化提取工具

用 LLM 从 jd_extractor 提取的 JD 正文中提取结构化字段。
将非结构化的 JD 文本转换为结构化的职位需求模型，
供后续的 matcher（简历-岗位匹配）使用。

设计思路：
1. 定义 JobRequirement Pydantic 模型，描述职位需求的结构
2. 用 LangChain 的 with_structured_output 让 LLM 直接返回结构化数据
   LLM 通过 function calling 被约束在 schema 内输出，可靠性高
3. 用 ChatPromptTemplate 构建提示词

为什么用 with_structured_output 而不是让 LLM 返回 JSON 字符串：
    传统做法是让 LLM 返回 JSON，再用 json.loads 解析。
    这很容易出错（LLM 可能返回不合法的 JSON、字段名不一致等）。
    with_structured_output 利用 function calling，
    LLM 被约束在 Pydantic schema 内输出，可靠性高得多。
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.model.model import MyModel


class JobRequirement(BaseModel):
    """职位需求结构化模型

    描述从 JD 文本中提取的结构化信息，供 matcher 进行简历-岗位匹配。
    """
    title: str = Field(description="职位名称，如'Agent应用开发工程师'")
    salary: str = Field(description="薪资范围，如'2-2.5万·13薪'或'7000-10000元'，无则填空字符串")
    location: str = Field(description="工作地点，如'北京 东城区'，无则填空字符串")
    experience: str = Field(description="经验要求，如'5-10年'或'经验不限'，无则填空字符串")
    education: str = Field(description="学历要求，如'本科'或'硕士'，无则填空字符串")
    skills: list[str] = Field(description="技能标签列表，如['Python', 'MySQL', 'LangChain']，无则空列表")
    responsibilities: list[str] = Field(description="岗位职责列表，每条职责为一个元素，无则空列表")
    qualifications: list[str] = Field(description="任职要求列表，每条要求为一个元素，无则空列表")


_SYSTEM_PROMPT = """你是一个职位描述分析专家。
你的任务是从招聘网站的 JD（职位描述）文本中提取结构化信息。

提取规则：
1. 只根据文本内容提取，不要编造文本中不存在的信息
2. 技能标签（skills）：提取文本中提到的所有技术、工具、框架关键词，如 Python、MySQL、LangChain 等
3. 岗位职责（responsibilities）：将"岗位职责"或"工作内容"部分的每一条作为列表的一个元素
4. 任职要求（qualifications）：将"任职要求"部分的每一条作为列表的一个元素
5. 如果某个字段在文本中找不到，填空字符串或空列表
6. 保留原文表述，不要改写或缩写
"""

_HUMAN_TEMPLATE = "请从以下 JD 文本中提取结构化信息：\n\n{jd_text}"


async def extract_requirements(jd_text: str) -> JobRequirement:
    """用 LLM 从 JD 文本中提取结构化职位需求。

    使用 LangChain 的 with_structured_output，通过 function calling
    让 LLM 返回符合 JobRequirement schema 的结构化数据。

    重构后是 async：chain.ainvoke 是 LangChain 原生 async 接口，
    配合 LangGraph 的 async 节点和 asyncio.gather 并发使用。

    Args:
        jd_text: jd_extractor.extract_jd_text() 返回的 JD 正文

    Returns:
        JobRequirement: 包含职位名、薪资、地点、技能、职责、要求等字段的结构化对象
    """
    model = MyModel.get_model()

    # with_structured_output: LLM 通过 function calling 返回符合 schema 的结构化数据
    # 比让 LLM 返回 JSON 字符串再 parse 可靠得多
    structured_model = model.with_structured_output(JobRequirement)

    # 构建提示词模板
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _HUMAN_TEMPLATE),
    ])

    # 构建 chain: prompt -> structured_model
    chain = prompt | structured_model

    result = await chain.ainvoke({"jd_text": jd_text})
    return result


async def main() -> None:
    """测试入口：抓取 URL → 提取 JD 正文 → LLM 结构化"""
    from app.tools.jd_fetcher import fetch_jd_from_url
    from app.tools.jd_extractor import extract_jd_text

    test_url = input("请输入招聘职位 URL: ").strip()
    if test_url:
        print(f"\n正在抓取: {test_url}")
        page_text = await fetch_jd_from_url(test_url)
        jd_text = extract_jd_text(page_text)
        print(f"\n=== JD 正文 ({len(jd_text)} 字符) ===")
        print(jd_text)

        print("\n=== 正在用 LLM 结构化 ===")
        result = await extract_requirements(jd_text)
        print("\n=== 结构化结果 ===")
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
