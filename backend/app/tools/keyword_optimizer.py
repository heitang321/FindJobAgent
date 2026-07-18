"""Tool 3.2 helpers merged into the section-rewriter workflow."""

from __future__ import annotations


def added_job_keywords(
    original_content: str,
    rewritten_content: str,
    job_keywords: list[str],
) -> list[str]:
    """Return job keywords newly present after a grounded rewrite."""
    original_lower = original_content.casefold()
    rewritten_lower = rewritten_content.casefold()
    return list(
        dict.fromkeys(
            keyword
            for keyword in job_keywords
            if keyword
            and keyword.casefold() not in original_lower
            and keyword.casefold() in rewritten_lower
        )
    )
