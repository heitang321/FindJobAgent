"""PDF layout-preserving editing tests for Agent 3."""

from __future__ import annotations

import sys
from pathlib import Path

import fitz
from docx import Document


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.tools.doc_generator import generate_resume_document  # noqa: E402
from app.tools.pdf_template_editor import (  # noqa: E402
    PdfTextEdit,
    apply_resume_pdf_edits,
    extract_resume_pdf_slots,
)


def _source_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((40, 45), "ORIGINAL RESUME", fontsize=20, fontname="hebo")
    page.insert_text((40, 90), "SELF EVALUATION", fontsize=15, fontname="hebo")
    page.insert_text(
        (40, 115),
        "Builds AI agents with Python and solves engineering problems.",
        fontsize=10,
    )
    page.insert_text((40, 175), "PROJECT EXPERIENCE", fontsize=15, fontname="hebo")
    page.insert_text((40, 205), "Resume Assistant", fontsize=12, fontname="hebo")
    page.insert_text((40, 230), "1. Architecture", fontsize=10)
    page.insert_text(
        (40, 250),
        "Implemented a Python service with FastAPI and WebSocket.",
        fontsize=10,
    )
    page.insert_text((40, 310), "SKILLS", fontsize=15, fontname="hebo")
    page.insert_text((40, 335), "1. Python, FastAPI, WebSocket", fontsize=10)
    document.save(path)
    document.close()


def test_extract_resume_pdf_slots_ignores_missing_work_section(tmp_path):
    source = tmp_path / "source.pdf"
    _source_pdf(source)

    slots = extract_resume_pdf_slots(
        source,
        {
            "work_experience",
            "project_experience",
            "self_evaluation",
            "skills",
        },
    )

    assert {slot.section_type for slot in slots} == {
        "project_experience",
        "self_evaluation",
        "skills",
    }
    assert any("Implemented a Python service" in slot.original_text for slot in slots)
    assert not any("Architecture" in slot.original_text for slot in slots)


def test_apply_pdf_edits_and_generate_word_preserve_page_geometry(tmp_path):
    source = tmp_path / "source.pdf"
    optimized_pdf = tmp_path / "optimized.pdf"
    optimized_docx = tmp_path / "optimized.docx"
    _source_pdf(source)
    slot = next(
        slot
        for slot in extract_resume_pdf_slots(source, {"project_experience"})
        if "Implemented" in slot.original_text
    )

    edit = PdfTextEdit(
        page_index=slot.page_index,
        rect=slot.rect,
        original_text=slot.original_text,
        rewritten_text="基于 Python 构建 FastAPI 与 WebSocket 服务。",
        font_size=slot.font_size,
        color=slot.color,
    )
    apply_resume_pdf_edits(source, optimized_pdf, [edit])

    with fitz.open(source) as before, fitz.open(optimized_pdf) as after:
        assert before.page_count == after.page_count == 1
        assert before[0].rect == after[0].rect
        assert "ORIGINAL RESUME" in after[0].get_text()
        assert "基于" in after[0].get_text()
        assert "构建" in after[0].get_text()
        assert "?" not in after[0].get_text()
        assert "Implemented a Python service" not in after[0].get_text()

    generate_resume_document(
        {},
        str(optimized_docx),
        source_document_path=str(source),
        pdf_text_edits=[edit],
    )

    generated = Document(optimized_docx)
    assert generated.sections[0].page_width.pt == 595
    assert generated.sections[0].page_height.pt == 842
    assert len(generated.inline_shapes) == 1
