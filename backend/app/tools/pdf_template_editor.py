"""Layout-preserving PDF text-slot extraction and replacement for Agent 3."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.schemas.optimization import SectionType


@dataclass(frozen=True)
class PdfTextSlot:
    """One editable visual text region in the source PDF."""

    section_type: SectionType
    section_index: int
    page_index: int
    rect: tuple[float, float, float, float]
    original_text: str
    font_size: float
    color: int


@dataclass(frozen=True)
class PdfTextEdit:
    """Verified replacement for one PDF text region."""

    page_index: int
    rect: tuple[float, float, float, float]
    original_text: str
    rewritten_text: str
    font_size: float
    color: int


@dataclass(frozen=True)
class _PdfLine:
    page_index: int
    page_width: float
    text: str
    rect: tuple[float, float, float, float]
    font_size: float
    font_name: str
    color: int

    @property
    def bold(self) -> bool:
        return (
            "bold" in self.font_name.casefold()
            or "semibold" in self.font_name.casefold()
        )


_SECTION_HEADINGS: dict[str, SectionType | None] = {
    "工作经历": "work_experience",
    "工作经验": "work_experience",
    "实习经历": "work_experience",
    "WORKEXPERIENCE": "work_experience",
    "项目经历": "project_experience",
    "项目经验": "project_experience",
    "PROJECTEXPERIENCE": "project_experience",
    "个人优势": "self_evaluation",
    "自我评价": "self_evaluation",
    "个人总结": "self_evaluation",
    "SELFEVALUATION": "self_evaluation",
    "PERSONALSUMMARY": "self_evaluation",
    "专业技能": "skills",
    "技能清单": "skills",
    "技能": "skills",
    "技术栈": "skills",
    "SKILLS": "skills",
    "TECHNICALSKILLS": "skills",
    "教育经历": None,
    "教育背景": None,
    "EDUCATION": None,
    "基本信息": None,
    "求职意向": None,
    "校园经历": None,
    "获奖经历": None,
    "资格证书": None,
    "证书": None,
    "CERTIFICATES": None,
    "语言能力": None,
}

_STRUCTURAL_LABELS = {
    "项目描述",
    "工作描述",
    "项目职责",
    "工作职责",
    "核心亮点",
    "技术亮点",
    "项目成果",
    "工作成果",
    "ARCHITECTURE",
    "PROJECTDESCRIPTION",
    "TECHNICALHIGHLIGHTS",
}


def _normalize_heading(text: str) -> str:
    return re.sub(r"[\s:：]", "", text).upper()


def _page_lines(page, page_index: int) -> list[_PdfLine]:
    import fitz

    lines: list[_PdfLine] = []
    data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "")]
            text = "".join(str(span.get("text", "")) for span in spans).strip()
            if not text or not spans:
                continue
            primary_span = max(spans, key=lambda span: len(str(span.get("text", ""))))
            lines.append(
                _PdfLine(
                    page_index=page_index,
                    page_width=float(page.rect.width),
                    text=text,
                    rect=tuple(float(value) for value in line["bbox"]),
                    font_size=float(primary_span.get("size") or 10),
                    font_name=str(primary_span.get("font") or ""),
                    color=int(primary_span.get("color") or 0),
                )
            )
    return sorted(lines, key=lambda item: (round(item.rect[1], 1), item.rect[0]))


def _is_entry_title(line: _PdfLine, section_type: SectionType) -> bool:
    return (
        section_type in {"work_experience", "project_experience"}
        and line.bold
        and line.font_size >= 11
        and len(line.text) <= 120
    )


def _is_numbered_label(text: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+[.、]\s*[^。！？!?；;]{1,30}", text))


def _is_editable_line(section_type: SectionType, line: _PdfLine) -> bool:
    text = line.text.strip()
    normalized = _normalize_heading(text)
    if not text or normalized in _STRUCTURAL_LABELS or "http" in text.casefold():
        return False
    if section_type == "project_experience":
        if _is_numbered_label(text):
            return False
        has_sentence_signal = any(mark in text for mark in "。.!?！？；;：:")
        if not has_sentence_signal and len(text) < 40:
            return False
    return True


def _starts_new_group(
    section_type: SectionType,
    previous: _PdfLine,
    current: _PdfLine,
) -> bool:
    if previous.page_index != current.page_index:
        return True
    vertical_gap = current.rect[1] - previous.rect[3]
    if vertical_gap > max(8.0, previous.font_size):
        return True
    if section_type == "skills" and re.match(r"^\s*\d+[.、]", current.text):
        return True
    if section_type in {
        "work_experience",
        "project_experience",
    } and previous.text.rstrip().endswith(("。", ".", "！", "!", "？", "?", "；", ";")):
        return True
    return False


def _slot_from_lines(
    section_type: SectionType,
    section_index: int,
    values: list[_PdfLine],
) -> PdfTextSlot:
    x0 = min(value.rect[0] for value in values)
    y0 = min(value.rect[1] for value in values) - 1.5
    x1 = max(value.rect[2] for value in values) + 2
    y1 = max(value.rect[3] for value in values) + 3
    return PdfTextSlot(
        section_type=section_type,
        section_index=section_index,
        page_index=values[0].page_index,
        rect=(x0, y0, x1, y1),
        original_text="".join(value.text for value in values),
        font_size=values[0].font_size,
        color=values[0].color,
    )


def extract_resume_pdf_slots(
    source_pdf_path: str | Path,
    targets: set[SectionType],
) -> list[PdfTextSlot]:
    """Extract editable visual text regions from requested resume sections."""
    import fitz

    source = Path(source_pdf_path).resolve()
    if source.suffix.casefold() != ".pdf" or not source.is_file():
        return []

    slots: list[PdfTextSlot] = []
    current_section: SectionType | None = None
    section_index = 0
    entry_started = False
    entry_has_content = False
    group: list[_PdfLine] = []

    def flush() -> None:
        nonlocal group, entry_has_content
        if current_section is not None and group:
            slots.append(_slot_from_lines(current_section, section_index, group))
            entry_has_content = True
        group = []

    with fitz.open(source) as document:
        for page_index, page in enumerate(document):
            for line in _page_lines(page, page_index):
                normalized = _normalize_heading(line.text)
                if normalized in _SECTION_HEADINGS:
                    flush()
                    current_section = _SECTION_HEADINGS[normalized]
                    section_index = 0
                    entry_started = False
                    entry_has_content = False
                    continue

                if current_section not in targets:
                    flush()
                    continue

                if _is_entry_title(line, current_section):
                    flush()
                    if entry_started and entry_has_content:
                        section_index += 1
                    entry_started = True
                    entry_has_content = False
                    continue

                if not _is_editable_line(current_section, line):
                    flush()
                    continue

                if group and _starts_new_group(current_section, group[-1], line):
                    flush()
                group.append(line)
            flush()

    return slots


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _rgb(color: int) -> tuple[float, float, float]:
    return (
        ((color >> 16) & 0xFF) / 255,
        ((color >> 8) & 0xFF) / 255,
        (color & 0xFF) / 255,
    )


def _font_configuration(text: str) -> tuple[str, str | None]:
    if text.isascii():
        return "helv", None
    candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    )
    font_path = next((path for path in candidates if path.is_file()), None)
    return ("ResumeCJK", str(font_path)) if font_path else ("china-s", None)


def _available_output_rect(
    page, edit: PdfTextEdit
) -> tuple[float, float, float, float]:
    """Use blank space on the same visual row without erasing neighbouring text."""
    import fitz

    source_rect = fitz.Rect(edit.rect)
    right_edge = max(source_rect.x1, page.rect.width - max(12.0, source_rect.x0))
    for word in page.get_text("words"):
        word_rect = fitz.Rect(word[:4])
        vertical_overlap = min(source_rect.y1, word_rect.y1) - max(
            source_rect.y0,
            word_rect.y0,
        )
        if vertical_overlap <= 1 or word_rect.intersects(source_rect):
            continue
        if word_rect.x0 > source_rect.x1:
            right_edge = min(right_edge, word_rect.x0 - 4)
    return (source_rect.x0, source_rect.y0, right_edge, source_rect.y1)


def _insert_fitted_text(
    page,
    edit: PdfTextEdit,
    output_rect: tuple[float, float, float, float],
) -> None:
    import fitz

    rect = fitz.Rect(output_rect)
    font_name, font_file = _font_configuration(edit.rewritten_text)
    if font_file:
        page.insert_font(fontname=font_name, fontfile=font_file)

    minimum_size = max(7.0, edit.font_size * 0.78)
    font_size = edit.font_size
    while font_size >= minimum_size:
        shape = page.new_shape()
        spare_height = shape.insert_textbox(
            rect,
            edit.rewritten_text,
            fontname=font_name,
            fontsize=font_size,
            color=_rgb(edit.color),
            align=fitz.TEXT_ALIGN_LEFT,
            lineheight=1.15,
        )
        if spare_height >= 0:
            shape.commit(overlay=True)
            return
        font_size -= 0.25
    raise ValueError(
        "Optimized text does not fit the original PDF text region without "
        "changing the template. Shorten the LLM output and retry."
    )


def apply_resume_pdf_edits(
    source_pdf_path: str | Path,
    output_pdf_path: str | Path,
    edits: Iterable[PdfTextEdit],
) -> str:
    """Replace verified PDF text regions while preserving page geometry."""
    import fitz

    source = Path(source_pdf_path).resolve()
    destination = Path(output_pdf_path).resolve()
    if source == destination:
        raise ValueError("Output PDF path must differ from the source path.")
    if source.suffix.casefold() != ".pdf" or not source.is_file():
        raise ValueError(
            "A valid source PDF is required for template-preserving output."
        )

    edit_list = list(edits)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(source) as document:
        output_rects: dict[int, tuple[float, float, float, float]] = {}
        for edit in edit_list:
            if edit.page_index < 0 or edit.page_index >= document.page_count:
                raise ValueError(f"PDF page {edit.page_index} no longer exists.")
            page = document[edit.page_index]
            actual_text = page.get_textbox(fitz.Rect(edit.rect))
            expected = _normalized_text(edit.original_text)
            actual = _normalized_text(actual_text)
            if expected not in actual and actual not in expected:
                raise ValueError(
                    "Source PDF content changed before optimization: "
                    f"page {edit.page_index + 1} text region does not match."
                )
            output_rects[id(edit)] = _available_output_rect(page, edit)

        pages_with_edits: dict[int, list[PdfTextEdit]] = {}
        for edit in edit_list:
            pages_with_edits.setdefault(edit.page_index, []).append(edit)

        for page_index, page_edits in pages_with_edits.items():
            page = document[page_index]
            for edit in page_edits:
                page.add_redact_annot(fitz.Rect(edit.rect), fill=(1, 1, 1))
            page.apply_redactions(images=0, graphics=0, text=0)
            for edit in page_edits:
                _insert_fitted_text(page, edit, output_rects[id(edit)])

        document.save(destination, garbage=4, deflate=True)

    return str(destination)
