"""三 Agent 联动测试（绕过网络，用预存 JD 数据）

Agent 1: 简历分析（DOCX → 结构化简历）— 真实运行
Agent 2: 岗位分析（预存 JD 正文 → 结构化 + 匹配 + gap）— 跳过 URL 抓取
Agent 3: 简历优化（结构化简历 + JD + gap → 优化简历 + DOCX）— 真实运行
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from app.schemas.workflow_state import initial_workflow_state
from app.agent.resume_analysis_agent import ResumeAnalysisAgent
from app.tools.jd_extractor import extract_jd_text
from app.tools.requirement_extractor import extract_requirements
from app.tools.matcher import analyze_match, split_to_workflow_fields
from app.agent.resume_optimization_agent import run_resume_optimization_agent

# 预存的 JD 页面文本（之前测试成功抓取的）
MOCK_JD_PAGE = """
Agent应用开发工程师
2-2.5万·13薪
北京 东城区
5-10年
本科
全职
招3人
职位描述
MySQL
Flask
C++
AGENT
AI
产业互联网平台
云计算
软件/IT服务
岗位职责：
1、基于大语言模型（LLM）开发 Agent 应用，设计并实现多步骤任务工作流（Workflow）。
2、使用 LangChain、LangGraph 或类似框架完成 Tool Calling、状态管理及 Agent 编排。
3、设计并实现基于 RAG 的知识库问答系统，包括文档切分、Embedding、向量检索及上下文管理等能力。结合 Prompt Engineering、Tool Calling 等技术，优化 Agent 的任务拆解、工具调用及执行效果。
4、参与 Agent 应用的系统架构设计与工程化部署，配合前后端完成产品落地。

任职要求：
1、熟悉 Python 开发，具备良好的工程代码能力。理解 Agent、RAG、Function Calling 等相关技术原理，并具备实际项目经验。
2、熟悉至少一种向量数据库或检索方案，如 Chroma、FAISS 等。具备较强的问题分析与自主学习能力，对 Agent 方向保持持续关注。
3、了解 MCP、A2A 等 Agent 协议或生态；了解 OpenClaw、Hermes-Agent 等开源 Agent 项目；有多 Agent 协作系统、知识库系统或 AI 产品落地经验；具备前后端或云服务部署经验。
工作地点
北京东城区环球贸易中心-C座18层
"""

# ===== 初始化 state =====
state = initial_workflow_state(task_id="test-3agent", file_path="uploads/test_resume.docx")
state["jd_url"] = "mock://offline-test"
state["jd_source_type"] = "url"

# ===== Agent 1: 简历分析 =====
print("=" * 60)
print("Agent 1: 简历分析（DOCX → 结构化简历）")
print("=" * 60)

agent1 = ResumeAnalysisAgent(use_configured_llm=True)
state = agent1.run(state)

print(f"stage: {state['current_stage']}")
if state.get("error"):
    print(f"ERROR: {state['error']}")
    sys.exit(1)

resume = state.get("structured_resume", {})
name = resume.get("basic_info", {}).get("name", "?")
skills = resume.get("skills", [])
print(f"简历姓名: {name}")
print(f"提取技能: {skills}")
print(f"工作经历: {len(resume.get('work_experience', []))}条")
print(f"项目经历: {len(resume.get('project_experience', []))}条")

# ===== Agent 2: 岗位分析（跳过 URL 抓取，用预存数据）=====
print()
print("=" * 60)
print("Agent 2: 岗位分析（预存 JD → 结构化 + 匹配）")
print("=" * 60)

# Tool 2.2: 提取 JD 正文
jd_text = extract_jd_text(MOCK_JD_PAGE)
state["jd_raw_text"] = jd_text
print(f"JD 正文: {len(jd_text)} 字符")

# Tool 2.3: LLM 结构化
print("LLM 结构化 JD...")
job_req = extract_requirements(jd_text)
state["job_requirements"] = job_req.model_dump()
print(f"职位: {job_req.title}")
print(f"技能要求: {job_req.skills[:10]}...")

# Tool 2.4: LLM 匹配
print("LLM 匹配分析...")
analysis = analyze_match(resume, job_req)
match_result, gap_report = split_to_workflow_fields(analysis)
state["match_result"] = match_result
state["gap_report"] = gap_report
print(f"匹配度: {match_result['overall_score']}/100")
print(f"已匹配: {match_result['matched_skills']}")
print(f"缺失: {match_result['missing_skills'][:10]}...")
print(f"关键差距: {len(gap_report['critical_gaps'])}条")

# ===== Agent 3: 简历优化 =====
print()
print("=" * 60)
print("Agent 3: 简历优化（LLM 改写 + DOCX 生成）")
print("=" * 60)

os.makedirs("outputs", exist_ok=True)
state = run_resume_optimization_agent(
    state,
    use_configured_llm=True,
    output_dir="outputs",
)

print(f"stage: {state['current_stage']}")
if state.get("error"):
    print(f"ERROR: {state['error']}")
    sys.exit(1)

opt = state.get("optimized_resume", {})
summary = state.get("optimization_summary", {})
file_path = state.get("output_file_path")

print(f"优化后技能: {opt.get('skills', [])}")
print(f"输出文件: {file_path}")
print(f"改写章节: {summary.get('rewritten_sections', [])}")
print(f"未变章节: {summary.get('unchanged_sections', [])}")
print(f"新增内容: {summary.get('added_count', 0)}处")
print(f"修改内容: {summary.get('modified_count', 0)}处")
print(f"新增关键词: {summary.get('added_keywords', [])}")

print()
print("=" * 60)
print("三 Agent 联动测试完成!")
print("=" * 60)
