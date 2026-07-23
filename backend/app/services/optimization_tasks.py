"""Agent 3 简历优化任务编排。

支持多版本优化策略：一次触发生成保守版、均衡版、激进版三个版本，
用户可在前端对比选择最满意的版本下载。
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from app.agent.resume_optimization_agent import run_resume_optimization_agent
from app.core.config import settings
from app.schemas.optimization import (
    STRATEGY_DESCRIPTIONS,
    STRATEGY_LABELS,
    OptimizationStrategy,
)
from app.schemas.workflow_state import WorkflowState
from app.services.resume_tasks import resume_task_store

_ALL_STRATEGIES: list[OptimizationStrategy] = ["conservative", "balanced", "aggressive"]


def prepare_optimization_task(task_id: str) -> WorkflowState:
    """校验前置条件，并将任务标记为可后台执行。"""
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)
    if not state.get("structured_resume"):
        raise ValueError("Resume analysis must finish before optimization.")
    if not state.get("job_requirements"):
        raise ValueError("Job analysis must finish before optimization.")
    if not state.get("match_result") and not state.get("gap_report"):
        raise ValueError(
            "Job match result or gap report is required before optimization."
        )

    state["current_stage"] = "optimizing"
    state["error"] = None
    state["optimized_resume"] = {}
    state["diff_report"] = {}
    state["optimization_summary"] = {}
    state["output_file_path"] = None
    state["optimization_versions"] = {}
    resume_task_store.update(state)
    return state


def _run_single_strategy(
    task_id: str,
    strategy: OptimizationStrategy,
) -> dict[str, str | dict | bool | None]:
    """运行单个策略的优化，返回该版本的结果快照。"""
    # 每次策略都从数据库重新读取最新 state，避免内存中串改
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)

    # 深拷贝避免修改原始 state
    strategy_state = deepcopy(state)
    strategy_state["current_stage"] = "optimizing"
    strategy_state["error"] = None
    strategy_state["optimized_resume"] = {}
    strategy_state["diff_report"] = {}
    strategy_state["output_file_path"] = None
    strategy_state["optimization_summary"] = {}

    output_dir = Path(settings.OPTIMIZATION_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 每个策略的输出文件名加上策略后缀，避免覆盖
    strategy_output_dir = output_dir / task_id
    strategy_output_dir.mkdir(parents=True, exist_ok=True)

    result = run_resume_optimization_agent(
        strategy_state,
        on_state_update=None,  # 不在单策略内部持久化，最后统一写
        use_configured_llm=settings.AI_ANALYSIS_ENABLED,
        max_workers=settings.OPTIMIZATION_MAX_WORKERS,
        output_dir=str(strategy_output_dir),
        strategy=strategy,
    )

    # 检查 agent 内部是否捕获了异常（run() 的 except 块会设置 error 字段）
    agent_error = result.get("error")
    if agent_error or result.get("current_stage") == "error":
        return {
            "strategy": strategy,
            "label": STRATEGY_LABELS[strategy],
            "description": STRATEGY_DESCRIPTIONS[strategy],
            "optimized_resume": {},
            "diff_report": {},
            "optimization_summary": {},
            "output_file_path": None,
            "download_ready": False,
            "error": agent_error or "优化执行失败",
        }

    output_path = result.get("output_file_path")
    return {
        "strategy": strategy,
        "label": STRATEGY_LABELS[strategy],
        "description": STRATEGY_DESCRIPTIONS[strategy],
        "optimized_resume": result.get("optimized_resume") or {},
        "diff_report": result.get("diff_report") or {},
        "optimization_summary": result.get("optimization_summary") or {},
        "output_file_path": output_path,
        "download_ready": bool(output_path and Path(output_path).is_file()),
    }


def optimize_resume_task(task_id: str) -> WorkflowState:
    """运行三种策略的 Agent 3 优化，并持久化最终结果。

    三种策略并行执行（保守/均衡/激进同时跑），总耗时 ≈ 最慢策略耗时
    而非三者之和。均衡版结果写入主字段（向后兼容旧接口）。
    """
    state = resume_task_store.get(task_id)
    if state is None:
        raise KeyError(task_id)

    versions: dict[str, dict] = {}
    start = time.time()

    with ThreadPoolExecutor(max_workers=3) as pool:
        future_map = {
            pool.submit(_run_single_strategy, task_id, strategy): strategy
            for strategy in _ALL_STRATEGIES
        }
        for future in future_map:
            strategy = future_map[future]
            try:
                versions[strategy] = future.result()
            except Exception as exc:
                versions[strategy] = {
                    "strategy": strategy,
                    "label": STRATEGY_LABELS[strategy],
                    "description": STRATEGY_DESCRIPTIONS[strategy],
                    "optimized_resume": {},
                    "diff_report": {},
                    "optimization_summary": {},
                    "output_file_path": None,
                    "download_ready": False,
                    "error": str(exc),
                }

    elapsed = time.time() - start
    print(
        f"[optimize] 三策略并行完成 task_id={task_id} 耗时={elapsed:.1f}s",
        flush=True,
    )

    # 均衡版写入主字段（向后兼容旧接口）
    balanced = versions.get("balanced", {})
    state["optimized_resume"] = balanced.get("optimized_resume") or {}
    state["diff_report"] = balanced.get("diff_report") or {}
    state["optimization_summary"] = balanced.get("optimization_summary") or {}
    state["output_file_path"] = balanced.get("output_file_path")
    state["optimization_versions"] = versions
    state["current_stage"] = "done"
    state["error"] = None
    resume_task_store.update(state)
    return state
