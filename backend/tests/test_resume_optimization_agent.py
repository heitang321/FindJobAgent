"""Agent 3 tools and orchestration tests."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from docx import Document


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.resume_optimization_agent import (  # noqa: E402
    run_resume_optimization_agent,
)
from app.schema.workflow_state import initial_workflow_state  # noqa: E402
from app.tools.diff_generator import diff_generator  # noqa: E402
from app.tools.doc_generator import generate_resume_document  # noqa: E402
from app.tools.section_rewriter import section_rewriter  # noqa: E402
from app.schemas.optimization import SectionRewriteRequest  # noqa: E402


def _resume() -> dict:
    return {
        "basic_info": {
            "name": "张三",
            "phone": "13800138000",
            "email": "zhang@example.com",
            "location": "上海",
        },
        "education": [
            {
                "school": "示例大学",
                "major": "计算机科学",
                "degree": "本科",
                "period": "2020-2024",
            }
        ],
        "work_experience": [
            {
                "company": "示例科技",
                "position": "后端工程师",
                "period": "2024-至今",
                "description": "负责接口开发",
            },
            {
                "company": "示例数据",
                "position": "实习生",
                "period": "2023-2024",
                "description": "参与数据处理",
            },
        ],
        "project_experience": [
            {
                "name": "招聘助手",
                "role": "开发者",
                "description": "使用 Python 开发简历分析功能",
            }
        ],
        "skills": ["Python", "FastAPI"],
        "self_evaluation": "学习能力强",
    }


def _state() -> dict:
    state = initial_workflow_state("optimization-test", "resume.docx")
    state["structured_resume"] = _resume()
    state["job_requirements"] = {
        "title": "AI 应用开发工程师",
        "skills": ["Python", "FastAPI", "LangChain"],
        "responsibilities": ["开发 Agent 应用"],
        "qualifications": ["熟悉 Python"],
    }
    state["match_result"] = {"missing_skills": ["LangChain"]}
    state["gap_report"] = {
        "sections": [
            {"section_type": "work_experience", "status": "weak"},
            {"section_type": "project_experience", "status": "weak"},
            {"section_type": "self_evaluation", "status": "covered"},
        ],
        "critical_gaps": ["工作和项目成果表达不够具体"],
    }
    return state


def test_section_rewriter_returns_requested_schema():
    request = SectionRewriteRequest(
        section_type="work_experience",
        original_content="负责接口开发",
        gap_report={"weak": ["work_experience"]},
        job_requirements={"skills": ["Python"]},
        job_keywords=["Python"],
    )

    def fake_llm(_prompt: str):
        return {
            "section_type": "ignored",
            "original_content": "ignored",
            "rewritten_content": "使用 Python 负责核心接口开发",
            "change_reason": "突出技术栈和职责",
            "changes": [{"type": "modified", "description": "明确 Python 技术栈"}],
        }

    result = section_rewriter(request, llm=fake_llm)

    assert result.section_type == "work_experience"
    assert result.original_content == "负责接口开发"
    assert result.rewritten_content == "使用 Python 负责核心接口开发"
    assert result.changes[0].type == "modified"


def test_diff_generator_produces_highlight_spans():
    original = _resume()
    optimized = _resume()
    optimized["self_evaluation"] = "学习能力强，具备团队协作意识"

    report = diff_generator(original, optimized)

    section = next(
        item for item in report.sections if item.section_type == "self_evaluation"
    )
    assert section.changed is True
    assert any(span.type == "added" for span in section.spans)


def test_doc_generator_creates_editable_resume_and_uses_template(tmp_path):
    template_path = tmp_path / "template.docx"
    template = Document()
    template.sections[0].header.paragraphs[0].text = "自定义简历模板"
    template.add_paragraph("模板占位内容")
    template.save(template_path)

    output_path = tmp_path / "optimized.docx"
    result = generate_resume_document(_resume(), str(output_path), str(template_path))

    generated = Document(result)
    body_text = "\n".join(paragraph.text for paragraph in generated.paragraphs)
    assert generated.sections[0].header.paragraphs[0].text == "自定义简历模板"
    assert "模板占位内容" not in body_text
    assert "张三" in body_text
    assert "负责接口开发" in body_text


def test_agent_rewrites_selected_sections_in_parallel(tmp_path):
    state = _state()
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def fake_llm(prompt: str):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1

        if '"original_content": "Python、FastAPI"' in prompt:
            rewritten = "Python、FastAPI、LangChain"
        elif "使用 Python 开发简历分析功能" in prompt:
            rewritten = "使用 Python 开发简历分析功能，完善 Agent 工作流"
        else:
            rewritten = "使用 Python 完成接口开发并提升交付效率"
        return {
            "rewritten_content": rewritten,
            "change_reason": "针对目标岗位强化表达",
            "changes": [{"type": "modified", "description": "强化岗位相关性"}],
        }

    final_state = run_resume_optimization_agent(
        state,
        llm=fake_llm,
        max_workers=4,
        output_dir=str(tmp_path),
    )

    assert final_state["current_stage"] == "done"
    assert maximum_active >= 2
    assert (
        state["structured_resume"]["work_experience"][0]["description"]
        == "负责接口开发"
    )
    assert (
        "提升交付效率"
        in final_state["optimized_resume"]["work_experience"][0]["description"]
    )
    assert "LangChain" in final_state["optimized_resume"]["skills"]
    assert final_state["optimized_resume"]["self_evaluation"] == "学习能力强"
    assert Path(final_state["output_file_path"]).is_file()
    assert final_state["diff_report"]["sections"]
    assert final_state["optimization_summary"]["modified_count"] >= 1
