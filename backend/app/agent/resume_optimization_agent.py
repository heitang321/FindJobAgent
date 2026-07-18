"""Agent 3: parallel, section-level resume optimization."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.workflow_state import WorkflowState
from app.tools.diff_generator import diff_generator
from app.tools.doc_generator import generate_resume_document
from app.tools.docx_template_editor import (
    DocumentTextEdit,
    extract_resume_text_slots,
)
from app.tools.keyword_optimizer import added_job_keywords
from app.tools.pdf_template_editor import PdfTextEdit, extract_resume_pdf_slots
from app.tools.section_rewriter import RewriteLLM, section_rewriter
from app.core.config import settings
from app.schemas.optimization import (
    OptimizationSummary,
    SectionRewriteRequest,
    SectionRewriteResult,
    SectionType,
)


StateCallback = Callable[[WorkflowState], None]


@dataclass(frozen=True)
class _SectionTask:
    section_type: SectionType
    section_index: int
    content: str
    evidence_context: str = ""
    document_paragraph_index: int | None = None
    pdf_page_index: int | None = None
    pdf_rect: tuple[float, float, float, float] | None = None
    pdf_font_size: float = 0
    pdf_color: int = 0

    @property
    def has_source_locator(self) -> bool:
        return (
            self.document_paragraph_index is not None or self.pdf_page_index is not None
        )


_SECTION_ALIASES: dict[str, SectionType] = {
    "work": "work_experience",
    "work_experience": "work_experience",
    "工作": "work_experience",
    "工作经历": "work_experience",
    "experience": "work_experience",
    "project": "project_experience",
    "project_experience": "project_experience",
    "项目": "project_experience",
    "项目经历": "project_experience",
    "self_evaluation": "self_evaluation",
    "summary": "self_evaluation",
    "自我评价": "self_evaluation",
    "个人优势": "self_evaluation",
    "skills": "skills",
    "skill": "skills",
    "技能": "skills",
    "专业技能": "skills",
}


def _section_name(value: Any) -> SectionType | None:
    if isinstance(value, dict):
        value = value.get("section_type") or value.get("section") or value.get("name")
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if normalized in _SECTION_ALIASES:
        return _SECTION_ALIASES[normalized]
    for alias, section_type in _SECTION_ALIASES.items():
        if alias in normalized:
            return section_type
    return None


def _target_sections(state: WorkflowState) -> set[SectionType]:
    gap_report = state.get("gap_report") or {}
    targets: set[SectionType] = set()
    covered: set[SectionType] = set()

    for key in ("missing", "weak", "missing_sections", "weak_sections"):
        for value in gap_report.get(key) or []:
            if section := _section_name(value):
                targets.add(section)

    for value in gap_report.get("sections") or []:
        if not isinstance(value, dict):
            continue
        section = _section_name(value)
        status = str(value.get("status") or "").casefold()
        if section and status in {"missing", "weak"}:
            targets.add(section)
        elif section and status == "covered":
            covered.add(section)

    missing_skills = (state.get("match_result") or {}).get("missing_skills") or []
    if missing_skills:
        targets.add("skills")

    gap_text = " ".join(
        str(item)
        for key in ("critical_gaps", "improvement_suggestions", "gap_summary")
        for item in (
            gap_report.get(key)
            if isinstance(gap_report.get(key), list)
            else [gap_report.get(key)]
        )
        if item
    ).casefold()
    keyword_groups = {
        "work_experience": ("工作", "经验", "职责", "成果", "experience"),
        "project_experience": ("项目", "技术", "架构", "project"),
        "self_evaluation": ("自我评价", "个人优势", "总结", "summary"),
        "skills": ("技能", "关键词", "skill", "keyword"),
    }
    text_targets: set[SectionType] = set()
    for section_type, keywords in keyword_groups.items():
        if any(keyword in gap_text for keyword in keywords):
            text_targets.add(section_type)  # type: ignore[arg-type]
    targets.update(text_targets)
    if gap_text and not targets:
        targets.update(
            {"work_experience", "project_experience", "self_evaluation", "skills"}
        )

    return targets - covered


def _section_tasks(
    structured_resume: dict[str, Any],
    targets: set[SectionType],
    source_document_path: str | None = None,
) -> list[_SectionTask]:
    tasks: list[_SectionTask] = []
    remaining_targets = set(targets)
    if source_document_path:
        source_path = Path(source_document_path)
        evidence_context = _resume_evidence_context(structured_resume)
        if source_path.suffix.casefold() == ".pdf":
            pdf_slots = extract_resume_pdf_slots(source_path, targets)
            tasks.extend(
                _SectionTask(
                    section_type=slot.section_type,
                    section_index=slot.section_index,
                    content=slot.original_text,
                    evidence_context=(
                        evidence_context if slot.section_type == "skills" else ""
                    ),
                    pdf_page_index=slot.page_index,
                    pdf_rect=slot.rect,
                    pdf_font_size=slot.font_size,
                    pdf_color=slot.color,
                )
                for slot in pdf_slots
            )
            located_sections = {slot.section_type for slot in pdf_slots}
            remaining_targets.clear()
        else:
            document_slots = extract_resume_text_slots(source_path, targets)
            tasks.extend(
                _SectionTask(
                    section_type=slot.section_type,
                    section_index=slot.section_index,
                    content=slot.original_text,
                    evidence_context=(
                        evidence_context if slot.section_type == "skills" else ""
                    ),
                    document_paragraph_index=slot.paragraph_index,
                )
                for slot in document_slots
            )
            located_sections = {slot.section_type for slot in document_slots}
            remaining_targets &= {"skills"}
        remaining_targets -= located_sections

    if "work_experience" in remaining_targets:
        for index, item in enumerate(structured_resume.get("work_experience") or []):
            content = str(item.get("description") or "").strip()
            if content:
                tasks.append(_SectionTask("work_experience", index, content))
    if "project_experience" in remaining_targets:
        for index, item in enumerate(structured_resume.get("project_experience") or []):
            content = str(item.get("description") or "").strip()
            if content:
                tasks.append(_SectionTask("project_experience", index, content))
    if "self_evaluation" in remaining_targets:
        content = str(structured_resume.get("self_evaluation") or "").strip()
        if content:
            tasks.append(_SectionTask("self_evaluation", 0, content))
    if "skills" in remaining_targets:
        skills = structured_resume.get("skills") or []
        content = "、".join(str(skill) for skill in skills if skill)
        evidence_context = _resume_evidence_context(structured_resume)
        if content or evidence_context:
            tasks.append(_SectionTask("skills", 0, content, evidence_context))
    return tasks


def _resume_evidence_context(structured_resume: dict[str, Any]) -> str:
    """Return only resume-owned facts that can support skill extraction."""
    evidence = {
        "work_experience": structured_resume.get("work_experience") or [],
        "project_experience": structured_resume.get("project_experience") or [],
        "self_evaluation": structured_resume.get("self_evaluation") or "",
    }
    return json.dumps(evidence, ensure_ascii=False, sort_keys=True)[:8000]


def _job_keywords(job_requirements: dict[str, Any]) -> list[str]:
    values = job_requirements.get("skills") or job_requirements.get("keywords") or []
    return list(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )


def _rewrite_tasks(
    tasks: list[_SectionTask],
    gap_report: dict[str, Any],
    job_requirements: dict[str, Any],
    llm: RewriteLLM | None,
    use_configured_llm: bool,
    max_workers: int,
) -> list[tuple[_SectionTask, SectionRewriteResult]]:
    keywords = _job_keywords(job_requirements)

    def rewrite(task: _SectionTask) -> tuple[_SectionTask, SectionRewriteResult]:
        request = SectionRewriteRequest(
            section_type=task.section_type,
            original_content=task.content,
            evidence_context=task.evidence_context,
            gap_report=gap_report,
            job_requirements=job_requirements,
            job_keywords=keywords,
        )
        return task, section_rewriter(
            request,
            llm=llm,
            use_configured_llm=use_configured_llm,
        )

    if not tasks:
        return []
    worker_count = max(1, min(max_workers, len(tasks)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(rewrite, tasks))


def _merge_rewrites(
    original_resume: dict[str, Any],
    rewritten: list[tuple[_SectionTask, SectionRewriteResult]],
) -> dict[str, Any]:
    optimized = deepcopy(original_resume)
    document_rewrites: dict[
        tuple[SectionType, int], list[tuple[_SectionTask, SectionRewriteResult]]
    ] = defaultdict(list)
    for task, result in rewritten:
        if task.has_source_locator:
            document_rewrites[(task.section_type, task.section_index)].append(
                (task, result)
            )
            continue
        content = result.rewritten_content.strip()
        if task.section_type == "work_experience":
            optimized["work_experience"][task.section_index]["description"] = content
        elif task.section_type == "project_experience":
            optimized["project_experience"][task.section_index]["description"] = content
        elif task.section_type == "self_evaluation":
            optimized["self_evaluation"] = content
        elif task.section_type == "skills":
            optimized["skills"] = [
                value.strip()
                for value in re.split(r"[,，、;；|\n]+", content)
                if value.strip()
            ]

    for (section_type, section_index), values in document_rewrites.items():
        if section_type in {"work_experience", "project_experience"}:
            entries = optimized.get(section_type) or []
            if section_index >= len(entries):
                continue
            original_description = str(entries[section_index].get("description") or "")
            description = original_description
            replacements_applied = False
            unmatched_rewrites: list[str] = []
            for task, result in values:
                if task.content in description:
                    description = description.replace(
                        task.content,
                        result.rewritten_content.strip(),
                        1,
                    )
                    replacements_applied = True
                else:
                    unmatched_rewrites.append(result.rewritten_content.strip())
            if not replacements_applied:
                description = "\n".join(
                    result.rewritten_content.strip() for _, result in values
                )
            elif unmatched_rewrites:
                description = "\n".join(
                    [description.rstrip(), *unmatched_rewrites]
                ).strip()
            entries[section_index]["description"] = description
        elif section_type == "self_evaluation":
            optimized["self_evaluation"] = "\n".join(
                result.rewritten_content.strip() for _, result in values
            )
        elif section_type == "skills":
            content = "、".join(
                result.rewritten_content.strip() for _, result in values
            )
            optimized["skills"] = [
                value.strip()
                for value in re.split(r"[,，、;；|\n]+", content)
                if value.strip()
            ]
    return optimized


def _source_resume_path(
    state: WorkflowState,
    explicit_source: str | None,
) -> str | None:
    for value in (
        explicit_source,
        state.get("file_path"),
        state.get("converted_file_path"),
    ):
        if not value:
            continue
        path = Path(value).resolve()
        if path.is_file() and path.suffix.casefold() in {".docx", ".pdf"}:
            return str(path)
    return None


def _document_output_edits(
    rewritten: list[tuple[_SectionTask, SectionRewriteResult]],
) -> list[DocumentTextEdit]:
    return [
        DocumentTextEdit(
            paragraph_index=task.document_paragraph_index,
            original_text=task.content,
            rewritten_text=result.rewritten_content,
        )
        for task, result in rewritten
        if task.document_paragraph_index is not None
        and result.rewritten_content.strip() != task.content.strip()
    ]


def _pdf_output_edits(
    rewritten: list[tuple[_SectionTask, SectionRewriteResult]],
) -> list[PdfTextEdit]:
    edits: list[PdfTextEdit] = []
    for task, result in rewritten:
        if (
            task.pdf_page_index is None
            or task.pdf_rect is None
            or result.rewritten_content.strip() == task.content.strip()
        ):
            continue
        edits.append(
            PdfTextEdit(
                page_index=task.pdf_page_index,
                rect=task.pdf_rect,
                original_text=task.content,
                rewritten_text=result.rewritten_content,
                font_size=task.pdf_font_size,
                color=task.pdf_color,
            )
        )
    return edits


def _missing_skills_text(
    rewritten: list[tuple[_SectionTask, SectionRewriteResult]],
) -> str:
    values = [
        result.rewritten_content.strip()
        for task, result in rewritten
        if task.section_type == "skills"
        and task.document_paragraph_index is None
        and result.rewritten_content.strip()
    ]
    return "、".join(values)


def _optimization_summary(
    report,
    rewritten: list[tuple[_SectionTask, SectionRewriteResult]],
    job_keywords: list[str],
) -> OptimizationSummary:
    rewritten_names = list(
        dict.fromkeys(
            f"{task.section_type}[{task.section_index}]"
            for task, result in rewritten
            if result.rewritten_content != result.original_content
        )
    )
    unchanged = list(
        dict.fromkeys(
            f"{section.section_type}[{section.section_index}]"
            for section in report.sections
            if not section.changed
        )
    )
    all_changes = [change for _, result in rewritten for change in result.changes]
    added_keywords: list[str] = []
    for _, result in rewritten:
        added_keywords.extend(
            added_job_keywords(
                result.original_content,
                result.rewritten_content,
                job_keywords,
            )
        )
    return OptimizationSummary(
        rewritten_sections=rewritten_names,
        unchanged_sections=unchanged,
        added_count=sum(change.type == "added" for change in all_changes),
        modified_count=sum(change.type == "modified" for change in all_changes),
        removed_count=sum(change.type == "removed" for change in all_changes),
        added_keywords=list(dict.fromkeys(added_keywords)),
    )


class ResumeOptimizationAgent:
    """Deep module that owns the complete Agent 3 optimization workflow."""

    def __init__(
        self,
        llm: RewriteLLM | None = None,
        on_state_update: StateCallback | None = None,
        use_configured_llm: bool = True,
        max_workers: int | None = None,
    ):
        self.llm = llm
        self.on_state_update = on_state_update
        self.use_configured_llm = use_configured_llm
        self.max_workers = max_workers or settings.OPTIMIZATION_MAX_WORKERS

    def _publish(self, state: WorkflowState) -> None:
        if self.on_state_update:
            self.on_state_update(state)

    def run(
        self,
        state: WorkflowState,
        output_dir: str | None = None,
        template_path: str | None = None,
    ) -> WorkflowState:
        try:
            original_resume = state.get("structured_resume") or {}
            if not original_resume:
                raise ValueError("Structured resume is required before optimization.")
            if not state.get("job_requirements"):
                raise ValueError("Job requirements are required before optimization.")

            state["current_stage"] = "optimizing"
            state["error"] = None
            state["optimized_resume"] = {}
            state["diff_report"] = {}
            state["output_file_path"] = None
            state["optimization_summary"] = {}
            self._publish(state)

            targets = _target_sections(state)
            if not targets:
                raise ValueError("No resume sections were selected for optimization.")
            source_document_path = _source_resume_path(state, template_path)
            tasks = _section_tasks(
                original_resume,
                targets,
                source_document_path=source_document_path,
            )
            if not tasks:
                raise ValueError(
                    "Selected resume sections contain no optimizable content."
                )
            rewritten = _rewrite_tasks(
                tasks,
                gap_report=state.get("gap_report") or {},
                job_requirements=state.get("job_requirements") or {},
                llm=self.llm,
                use_configured_llm=self.use_configured_llm and self.llm is None,
                max_workers=self.max_workers,
            )
            optimized_resume = _merge_rewrites(original_resume, rewritten)
            rewrite_results = [result for _, result in rewritten]
            report = diff_generator(original_resume, optimized_resume, rewrite_results)

            destination_dir = Path(output_dir or settings.OPTIMIZATION_OUTPUT_DIR)
            destination = destination_dir / f"{state['task_id']}_optimized_resume.docx"
            output_path = generate_resume_document(
                optimized_resume,
                str(destination),
                source_document_path=source_document_path,
                text_edits=_document_output_edits(rewritten),
                pdf_text_edits=_pdf_output_edits(rewritten),
                missing_skills_text=_missing_skills_text(rewritten),
            )
            summary = _optimization_summary(
                report,
                rewritten,
                _job_keywords(state.get("job_requirements") or {}),
            )

            state["optimized_resume"] = optimized_resume
            state["diff_report"] = report.model_dump()
            state["output_file_path"] = output_path
            state["optimization_summary"] = summary.model_dump()
            state["current_stage"] = "done"
            self._publish(state)
            return state
        except Exception as exc:
            state["current_stage"] = "error"
            state["error"] = str(exc)
            self._publish(state)
            return state


def run_resume_optimization_agent(
    state: WorkflowState,
    llm: RewriteLLM | None = None,
    on_state_update: StateCallback | None = None,
    use_configured_llm: bool = True,
    max_workers: int | None = None,
    output_dir: str | None = None,
    template_path: str | None = None,
) -> WorkflowState:
    """Run Agent 3 through its single public interface."""
    return ResumeOptimizationAgent(
        llm=llm,
        on_state_update=on_state_update,
        use_configured_llm=use_configured_llm,
        max_workers=max_workers,
    ).run(state, output_dir=output_dir, template_path=template_path)
