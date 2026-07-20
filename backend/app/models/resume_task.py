"""简历任务表 ORM 模型，对应 MySQL resume_tasks 表。

存储完整的 WorkflowState，三个 Agent 的产出都持久化到此表。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ResumeTask(Base):
    """简历任务表，主键为 VARCHAR(64) task_id。

    存储三阶段工作流的完整状态：
    - Agent 1: file_path, file_type, converted_file_path, raw_text,
      structured_resume, resume_evaluation
    - Agent 2: jd_source_type, jd_raw_text, job_requirements, match_result, gap_report
    - Agent 3: optimized_resume, diff_report, output_file_path, optimization_summary
    """

    __tablename__ = "resume_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # 通用状态
    current_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="upload"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Agent 1 产出
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    converted_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    structured_resume: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    resume_evaluation: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Agent 2 产出
    jd_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_source_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    jd_raw_text: Mapped[str | None] = mapped_column(LONGTEXT, nullable=True)
    job_requirements: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    match_result: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    gap_report: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    job_search_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    selected_jd_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Agent 3 产出
    optimized_resume: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    diff_report: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    output_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    optimization_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    def __repr__(self) -> str:
        return f"<ResumeTask(task_id={self.task_id!r}, stage={self.current_stage!r})>"
