"""Tool 1.2: convert PDF resumes into a layout-preserving Word reference.

PDF text is not reconstructed into editable Word paragraphs because that can
reorder content and destroy the original template. Each PDF page is rendered
once and embedded as a full-page image, preserving the visible source exactly.
Agent analysis reads the original PDF separately.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path


_PDF_RENDER_SCALE = 2


def _build_layout_preserving_docx(pdf_path: Path, output_path: Path) -> None:
    """Embed rendered PDF pages in a Word document without text reflow."""
    import fitz
    from docx import Document
    from docx.enum.text import WD_BREAK, WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run()

    with fitz.open(str(pdf_path)) as pdf:
        if pdf.page_count == 0:
            raise ValueError("PDF contains no pages")

        first_page = pdf[0]
        section = document.sections[0]
        section.page_width = Pt(first_page.rect.width)
        section.page_height = Pt(first_page.rect.height)
        section.top_margin = Pt(0)
        section.bottom_margin = Pt(0)
        section.left_margin = Pt(0)
        section.right_margin = Pt(0)
        section.header_distance = Pt(0)
        section.footer_distance = Pt(0)

        matrix = fitz.Matrix(_PDF_RENDER_SCALE, _PDF_RENDER_SCALE)
        for index, page in enumerate(pdf):
            if index:
                run.add_break(WD_BREAK.PAGE)
            page_png = page.get_pixmap(matrix=matrix, alpha=False).tobytes("png")
            run.add_picture(
                BytesIO(page_png),
                width=Pt(page.rect.width),
                height=Pt(page.rect.height),
            )

    document.save(output_path)


def pdf_to_word_converter(file_path: str) -> dict[str, object]:
    """Convert PDF to a visually faithful DOCX; pass DOCX through unchanged.

    The PDF result is intended as a read-only reference preserving the source
    template. It is deliberately image-based and should not be used as the
    editable Agent 3 optimization output.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return {"converted_path": str(path), "success": True}
    if suffix != ".pdf":
        return {"converted_path": str(path), "success": False}

    converted_path = path.with_suffix(".docx")
    try:
        _build_layout_preserving_docx(path, converted_path)
    except Exception:
        return {"converted_path": str(converted_path), "success": False}

    return {"converted_path": str(converted_path), "success": converted_path.exists()}
