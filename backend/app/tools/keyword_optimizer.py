"""Tool 3.2：供段落改写流程使用的关键词辅助工具。"""

from __future__ import annotations


def added_job_keywords(
    original_content: str,
    rewritten_content: str,
    job_keywords: list[str],
) -> list[str]:
    """返回基于事实改写后新融入的岗位关键词。"""
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
