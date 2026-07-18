"""Tool 3.4: build frontend-ready resume section comparisons."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from difflib import SequenceMatcher
from typing import Any

from app.schemas.optimization import (
    DiffReport,
    DiffSpan,
    SectionDiff,
    SectionRewriteResult,
)


def _display_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _flatten_resume(resume: dict[str, Any]) -> list[tuple[str, int, str]]:
    records: list[tuple[str, int, str]] = []
    records.append(("basic_info", 0, _display_content(resume.get("basic_info", {}))))
    for section_type in ("education", "work_experience", "project_experience"):
        values = resume.get(section_type) or []
        for index, value in enumerate(values):
            records.append((section_type, index, _display_content(value)))
    records.append(("skills", 0, _display_content(resume.get("skills", []))))
    records.append(
        ("self_evaluation", 0, _display_content(resume.get("self_evaluation", "")))
    )
    return records


def _diff_spans(original: str, optimized: str) -> list[DiffSpan]:
    spans: list[DiffSpan] = []
    matcher = SequenceMatcher(None, original, optimized)
    for operation, i1, i2, j1, j2 in matcher.get_opcodes():
        if operation == "equal":
            spans.append(
                DiffSpan(
                    type="equal",
                    original_text=original[i1:i2],
                    optimized_text=optimized[j1:j2],
                )
            )
        elif operation == "insert":
            spans.append(DiffSpan(type="added", optimized_text=optimized[j1:j2]))
        elif operation == "delete":
            spans.append(DiffSpan(type="removed", original_text=original[i1:i2]))
        else:
            spans.append(
                DiffSpan(
                    type="modified",
                    original_text=original[i1:i2],
                    optimized_text=optimized[j1:j2],
                )
            )
    return spans


def diff_generator(
    original_resume: dict[str, Any],
    optimized_resume: dict[str, Any],
    rewrite_results: list[SectionRewriteResult] | None = None,
) -> DiffReport:
    """Compare every section occurrence and attach rewrite explanations."""
    original = {
        (kind, index): text for kind, index, text in _flatten_resume(original_resume)
    }
    optimized = {
        (kind, index): text for kind, index, text in _flatten_resume(optimized_resume)
    }

    explanations: dict[str, deque[SectionRewriteResult]] = defaultdict(deque)
    for result in rewrite_results or []:
        explanations[result.section_type].append(result)

    sections: list[SectionDiff] = []
    keys = list(dict.fromkeys([*original.keys(), *optimized.keys()]))
    for section_type, section_index in keys:
        original_content = original.get((section_type, section_index), "")
        optimized_content = optimized.get((section_type, section_index), "")
        rewrite = (
            explanations[section_type].popleft() if explanations[section_type] else None
        )
        sections.append(
            SectionDiff(
                section_type=section_type,
                section_index=section_index,
                original_content=original_content,
                optimized_content=optimized_content,
                changed=original_content != optimized_content,
                change_reason=rewrite.change_reason if rewrite else "",
                changes=rewrite.changes if rewrite else [],
                spans=_diff_spans(original_content, optimized_content),
            )
        )
    return DiffReport(sections=sections)
