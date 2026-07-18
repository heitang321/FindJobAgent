"""Pydantic 请求/响应模型 (Schema)。

按业务模块拆分文件，如 user.py、resume.py 等。
"""

from app.schemas.optimization import (
    DiffReport,
    OptimizationResultResponse,
    OptimizationSummary,
    OptimizationTriggerResponse,
    SectionChange,
    SectionDiff,
    SectionRewriteRequest,
    SectionRewriteResult,
)
from app.schemas.workflow_state import WorkflowState, initial_workflow_state

__all__ = [
    "DiffReport",
    "OptimizationResultResponse",
    "OptimizationSummary",
    "OptimizationTriggerResponse",
    "SectionChange",
    "SectionDiff",
    "SectionRewriteRequest",
    "SectionRewriteResult",
    "WorkflowState",
    "initial_workflow_state",
]
