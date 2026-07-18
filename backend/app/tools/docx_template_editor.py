"""Layout-preserving DOCX text-slot extraction and editing.

Only ``word/document.xml`` is rewritten. All styles, relationships, media,
headers, footers, settings, and document properties are copied byte-for-byte
from the user's source document.
"""

from __future__ import annotations

import tempfile
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from app.schemas.optimization import SectionType


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_NS = {"w": _W_NS}
_DOCUMENT_PART = "word/document.xml"


@dataclass(frozen=True)
class ResumeTextSlot:
    """One source paragraph that may be rewritten without rebuilding layout."""

    section_type: SectionType
    section_index: int
    paragraph_index: int
    original_text: str


@dataclass(frozen=True)
class DocumentTextEdit:
    """Verified in-place replacement for one source paragraph."""

    paragraph_index: int
    original_text: str
    rewritten_text: str


_SECTION_HEADINGS: dict[str, SectionType | None] = {
    "工作经历": "work_experience",
    "工作经验": "work_experience",
    "实习经历": "work_experience",
    "项目经历": "project_experience",
    "项目经验": "project_experience",
    "个人优势": "self_evaluation",
    "自我评价": "self_evaluation",
    "个人总结": "self_evaluation",
    "专业技能": "skills",
    "技能清单": "skills",
    "技能": "skills",
    "技术栈": "skills",
    "教育经历": None,
    "教育背景": None,
    "基本信息": None,
    "求职意向": None,
    "校园经历": None,
    "获奖经历": None,
    "资格证书": None,
    "证书": None,
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
    "高性能与高可用",
    "现代化前端体验",
}


def _normalize_heading(text: str) -> str:
    return "".join(text.strip().rstrip("：:").split())


def _parse_document_xml(data: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return etree.fromstring(data, parser=parser)


def _paragraphs(root: etree._Element) -> list[etree._Element]:
    return root.xpath("/w:document/w:body//w:p", namespaces=_NS)


def _text_nodes(paragraph: etree._Element) -> list[etree._Element]:
    return paragraph.xpath(".//w:t", namespaces=_NS)


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(node.text or "" for node in _text_nodes(paragraph)).strip()


def _run_is_bold(run: etree._Element) -> bool:
    bold = run.find("w:rPr/w:b", namespaces=_NS)
    return bold is not None and bold.get(f"{{{_W_NS}}}val", "1") not in {
        "0",
        "false",
        "off",
    }


def _is_bold_title(paragraph: etree._Element, text: str) -> bool:
    runs = paragraph.xpath(".//w:r[w:t]", namespaces=_NS)
    visible_lengths = [
        sum(len(node.text or "") for node in run.xpath(".//w:t", namespaces=_NS))
        for run in runs
    ]
    total = sum(visible_lengths)
    if not total:
        return False
    bold_length = sum(
        length for run, length in zip(runs, visible_lengths) if _run_is_bold(run)
    )
    return bold_length / total >= 0.75 and len(text) <= 100


def _is_editable_content(section_type: SectionType, text: str) -> bool:
    normalized = _normalize_heading(text)
    if not normalized or normalized in _STRUCTURAL_LABELS:
        return False
    if section_type == "project_experience":
        has_sentence_signal = any(mark in text for mark in "。.!?！？；;：:")
        if not has_sentence_signal and len(text) < 40:
            return False
    return True


def _read_document_root(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as archive:
        return _parse_document_xml(archive.read(_DOCUMENT_PART))


def extract_resume_text_slots(
    source_document_path: str | Path,
    targets: set[SectionType],
) -> list[ResumeTextSlot]:
    """Locate editable resume paragraphs inside the requested semantic sections."""
    path = Path(source_document_path).resolve()
    if path.suffix.casefold() != ".docx" or not path.is_file():
        return []

    root = _read_document_root(path)
    slots: list[ResumeTextSlot] = []
    current_section: SectionType | None = None
    section_index = 0
    entry_started = False
    entry_has_content = False

    for paragraph_index, paragraph in enumerate(_paragraphs(root)):
        text = _paragraph_text(paragraph)
        normalized = _normalize_heading(text)
        if normalized in _SECTION_HEADINGS:
            current_section = _SECTION_HEADINGS[normalized]
            section_index = 0
            entry_started = False
            entry_has_content = False
            continue

        if current_section not in targets or not text:
            continue

        if current_section in {"work_experience", "project_experience"} and (
            _is_bold_title(paragraph, text)
        ):
            if entry_started and entry_has_content:
                section_index += 1
            entry_started = True
            entry_has_content = False
            continue

        if not _is_editable_content(current_section, text):
            continue

        slots.append(
            ResumeTextSlot(
                section_type=current_section,
                section_index=section_index,
                paragraph_index=paragraph_index,
                original_text=text,
            )
        )
        entry_has_content = True

    return slots


def _set_space_preservation(node: etree._Element, text: str) -> None:
    attribute = f"{{{_XML_NS}}}space"
    if text.startswith(" ") or text.endswith(" "):
        node.set(attribute, "preserve")
    elif attribute in node.attrib:
        del node.attrib[attribute]


def _replace_paragraph_text(paragraph: etree._Element, replacement: str) -> None:
    nodes = _text_nodes(paragraph)
    if not nodes:
        raise ValueError("The selected DOCX paragraph does not contain editable text.")

    original_lengths = [len(node.text or "") for node in nodes]
    total = sum(original_lengths)
    if total <= 0:
        nodes[0].text = replacement
        _set_space_preservation(nodes[0], replacement)
        return

    consumed_original = 0
    consumed_replacement = 0
    replacement_length = len(replacement)
    for index, (node, original_length) in enumerate(zip(nodes, original_lengths)):
        consumed_original += original_length
        end = (
            replacement_length
            if index == len(nodes) - 1
            else round(replacement_length * consumed_original / total)
        )
        segment = replacement[consumed_replacement:end]
        node.text = segment
        _set_space_preservation(node, segment)
        consumed_replacement = end


def _coerce_edit(value: DocumentTextEdit | dict[str, Any]) -> DocumentTextEdit:
    if isinstance(value, DocumentTextEdit):
        return value
    return DocumentTextEdit(
        paragraph_index=int(value["paragraph_index"]),
        original_text=str(value["original_text"]),
        rewritten_text=str(value["rewritten_text"]),
    )


def _append_missing_skills(root: etree._Element, skills_text: str) -> None:
    paragraphs = _paragraphs(root)
    existing_heading = next(
        (
            paragraph
            for paragraph in paragraphs
            if _SECTION_HEADINGS.get(_normalize_heading(_paragraph_text(paragraph)))
            == "skills"
        ),
        None,
    )

    heading_template = next(
        (
            paragraph
            for paragraph in paragraphs
            if _normalize_heading(_paragraph_text(paragraph))
            in {"教育经历", "工作经历", "项目经历", "个人优势", "自我评价"}
        ),
        None,
    )
    body_template = next(
        (
            paragraph
            for paragraph in paragraphs
            if _paragraph_text(paragraph)
            and _normalize_heading(_paragraph_text(paragraph)) not in _SECTION_HEADINGS
            and not _is_bold_title(paragraph, _paragraph_text(paragraph))
        ),
        None,
    )
    if body_template is None or (heading_template is None and existing_heading is None):
        raise ValueError(
            "The source resume has no reusable style for a skills section."
        )

    body = deepcopy(body_template)
    _replace_paragraph_text(body, skills_text)

    if existing_heading is not None:
        parent = existing_heading.getparent()
        if parent is None:
            raise ValueError("Invalid DOCX: skills heading has no parent element.")
        parent.insert(parent.index(existing_heading) + 1, body)
        return

    heading = deepcopy(heading_template)
    _replace_paragraph_text(heading, "专业技能")

    document_body = root.find("w:body", namespaces=_NS)
    if document_body is None:
        raise ValueError("Invalid DOCX: word/document.xml has no body.")
    section_properties = document_body.find("w:sectPr", namespaces=_NS)
    insertion_index = (
        document_body.index(section_properties)
        if section_properties is not None
        else len(document_body)
    )
    document_body.insert(insertion_index, heading)
    document_body.insert(insertion_index + 1, body)


def apply_resume_text_edits(
    source_document_path: str | Path,
    output_path: str | Path,
    edits: Iterable[DocumentTextEdit | dict[str, Any]],
    *,
    missing_skills_text: str = "",
) -> str:
    """Copy a source DOCX and change only verified body text slots."""
    source = Path(source_document_path).resolve()
    destination = Path(output_path).resolve()
    if source == destination:
        raise ValueError("Output path must differ from the source resume path.")
    if source.suffix.casefold() != ".docx" or not source.is_file():
        raise ValueError(
            "A valid source DOCX is required for layout-preserving output."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        document_xml = archive.read(_DOCUMENT_PART)
        root = _parse_document_xml(document_xml)
        paragraphs = _paragraphs(root)

        for raw_edit in edits:
            edit = _coerce_edit(raw_edit)
            try:
                paragraph = paragraphs[edit.paragraph_index]
            except IndexError as exc:
                raise ValueError(
                    f"DOCX paragraph {edit.paragraph_index} no longer exists."
                ) from exc
            actual_text = _paragraph_text(paragraph)
            if actual_text != edit.original_text.strip():
                raise ValueError(
                    "Source resume content changed before optimization: "
                    f"paragraph {edit.paragraph_index} does not match."
                )
            _replace_paragraph_text(paragraph, edit.rewritten_text.strip())

        if missing_skills_text.strip():
            _append_missing_skills(root, missing_skills_text.strip())

        updated_xml = etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.stem}-",
            suffix=".docx",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        try:
            with zipfile.ZipFile(temporary_path, "w") as output_archive:
                output_archive.comment = archive.comment
                for item in archive.infolist():
                    data = (
                        updated_xml
                        if item.filename == _DOCUMENT_PART
                        else archive.read(item.filename)
                    )
                    output_archive.writestr(item, data)
            temporary_path.replace(destination)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    return str(destination)
