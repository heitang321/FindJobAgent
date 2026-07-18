r"""Manual test script for Agent 1 resume upload and format-preserving output.

Usage:
    python backend/scripts/test_resume_upload.py
    python backend/scripts/test_resume_upload.py C:\path\to\resume.pdf

The script copies the input resume into uploads/resumes/manual-tests, runs
Agent 1, then writes:
    - outputs/resumes/<task_id>_analysis.json
    - outputs/resumes/<task_id>_converted_resume.<ext>
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.resume_analysis_agent import run_resume_analysis_agent  # noqa: E402
from app.schema.workflow_state import initial_workflow_state  # noqa: E402


def _ask_resume_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()

    raw = input("请输入简历文件路径（pdf/docx）：").strip().strip('"')
    return Path(raw).expanduser().resolve()


def _copy_upload_file(source: Path, task_id: str) -> Path:
    upload_dir = BACKEND_ROOT.parent / "uploads" / "resumes" / "manual-tests" / task_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / source.name
    shutil.copy2(source, target)
    return target


def _copy_format_preserving_resume(state: dict, output_dir: Path, task_id: str) -> Path:
    """Copy the converted/original resume without rebuilding its content.

    Agent 1 may analyze text, but it must not rewrite the resume template. For
    DOCX input this copies the original DOCX. For PDF input this copies the
    pdf2docx conversion result.
    """
    converted_path = state.get("converted_file_path")
    source_path = Path(converted_path or state["file_path"])
    suffix = source_path.suffix or Path(state["file_path"]).suffix
    output_path = output_dir / f"{task_id}_converted_resume{suffix}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, output_path)
    return output_path


def main() -> int:
    source = _ask_resume_path()
    if not source.exists() or not source.is_file():
        print(f"文件不存在：{source}")
        return 1

    task_id = uuid4().hex
    uploaded_path = _copy_upload_file(source, task_id)

    state = initial_workflow_state(task_id=task_id, file_path=str(uploaded_path))
    final_state = run_resume_analysis_agent(state)

    output_dir = BACKEND_ROOT.parent / "outputs" / "resumes"
    analysis_path = output_dir / f"{task_id}_analysis.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis_path.write_text(
        json.dumps(final_state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    converted_resume_path = None
    if final_state.get("current_stage") == "done":
        converted_resume_path = _copy_format_preserving_resume(final_state, output_dir, task_id)

    print("简历分析完成")
    print(f"任务 ID：{task_id}")
    print(f"当前状态：{final_state.get('current_stage')}")
    evaluation = final_state.get("resume_evaluation") or {}
    if evaluation:
        print(f"分析来源：{evaluation.get('analysis_source') or 'unknown'}")
        if evaluation.get("llm_error"):
            print(f"AI 调用信息：{evaluation['llm_error']}")
    if final_state.get("error"):
        print(f"错误信息：{final_state['error']}")
    print(f"分析 JSON：{analysis_path}")
    if converted_resume_path:
        print(f"格式转换文件（未改写内容）：{converted_resume_path}")
    return 0 if final_state.get("current_stage") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
