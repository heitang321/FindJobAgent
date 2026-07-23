"""智能问答路由（SSE 流式输出）。

用户提交问题后：
1. 加载会话历史消息作为上下文（记忆功能）
2. 保存用户消息到 MySQL
3. 根据关键词路由：
   - 文本类（qa/analysis/interview/salary/resume_advice）→ 逐 token 流式输出
   - 图表类（chart）→ 先发"生成中"提示，再一次性返回完整 JSON
   - 岗位搜索（job_search）→ 先发"搜索中"提示，再返回岗位卡片
4. 保存 AI 回复到 MySQL
5. 返回 session_id 供前端下次传参

SSE 事件格式：
  data: {"type": "start", "msg_type": "qa", "session_id": "xxx"}
  data: {"type": "delta", "content": "你好"}
  data: {"type": "chart", "data": "{...json...}"}
  data: {"type": "job_search", "data": "[...]", "keywords": "Python"}
  data: {"type": "end", "session_id": "xxx"}
"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.chat_agent import STREAMABLE_TYPES, get_chat_agent
from app.api.deps import CurrentUser
from app.core.redis_client import (
    get_cached_search,
    get_session_search,
    save_session_search,
    set_cached_search,
)
from app.models.chat_session import (
    add_message,
    create_session,
    delete_session,
    get_session_messages,
    list_user_sessions,
    update_session_title,
)
from app.model.openai_compatible import chat_completion_stream

router = APIRouter()


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    context: str = Field("", description="可选上下文")
    session_id: str | None = Field(None, description="会话 ID，首次不传则自动创建")


def _sse(data: dict) -> str:
    """格式化 SSE 事件。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _summarize_job_search(content: str, keywords: str = "") -> str:
    """将岗位搜索结果 JSON 转为 LLM 可读的文本摘要。"""
    try:
        cards = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return f"[搜索了{keywords}相关岗位]"

    if not isinstance(cards, list) or not cards:
        return f"[搜索了{keywords}相关岗位，但未找到结果]"

    lines = [f"搜索到了以下{len(cards)}个{keywords}相关岗位："]
    for i, card in enumerate(cards, 1):
        title = card.get("title", "")
        company = card.get("company", "")
        salary = card.get("salary", "")
        location = card.get("location", "")
        skills = card.get("skills", [])
        experience = card.get("experience", "")
        education = card.get("education", "")

        skill_str = "、".join(skills[:6]) if skills else ""
        parts = [f"{i}. {title}"]
        if company: parts.append(f"公司：{company}")
        if salary: parts.append(f"薪资：{salary}")
        if location: parts.append(f"地点：{location}")
        if experience: parts.append(f"经验：{experience}")
        if education: parts.append(f"学历：{education}")
        if skill_str: parts.append(f"技能要求：{skill_str}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


def _build_history(raw_msgs: list[dict], limit: int = 10) -> list[dict]:
    """将数据库消息转为 LLM history 格式（最近 N 条）。

    图表/岗位搜索等非文本消息用占位符替代，避免 JSON 混入历史。
    岗位搜索结果转为文本摘要，让 LLM 能分析后续提问。
    """
    history: list[dict] = []
    for m in raw_msgs[-limit:]:
        role = m.get("role")
        content = m.get("content", "")
        msg_type = m.get("type", "qa")

        if role == "user":
            history.append({"role": "user", "content": content})
        elif role == "assistant":
            if msg_type in STREAMABLE_TYPES:
                # 截断过长内容
                if len(content) > 800:
                    content = content[:800] + "..."
                history.append({"role": "assistant", "content": content})
            elif msg_type == "chart":
                history.append({"role": "assistant", "content": "[生成了一个图表]"})
            elif msg_type == "job_search":
                kw = m.get("keywords", "")
                summary = _summarize_job_search(content, kw)
                history.append({"role": "assistant", "content": summary})
            # error 类型跳过
    return history


@router.post("/chat", summary="智能问答（SSE 流式输出）")
async def chat(payload: ChatRequest, user: CurrentUser):
    """流式智能问答，支持多轮记忆和 SSE 输出。"""

    async def event_generator():
        agent = get_chat_agent()
        question = payload.question.strip()
        q = question

        # 1. 会话管理
        session_id = payload.session_id
        if not session_id:
            session_id = uuid4().hex
            title = question[:30] + ("..." if len(question) > 30 else "")
            await asyncio.to_thread(create_session, session_id, user["id"], title)

        # 2. 加载历史消息（此时不含当前问题，因为还没保存）
        raw_msgs = await asyncio.to_thread(get_session_messages, session_id)
        history = _build_history(raw_msgs)

        # 3. 保存用户消息
        await asyncio.to_thread(add_message, session_id, "user", question, "user")

        # 4. 路由判断
        route_type = agent.route(q)

        # 5. 发送 start 事件
        yield _sse({"type": "start", "msg_type": route_type, "session_id": session_id})

        # 6. 按类型处理
        if route_type in STREAMABLE_TYPES:
            # ===== 文本类：流式输出 =====
            system = agent.get_system_prompt(route_type)
            full_text = ""
            try:
                for chunk in chat_completion_stream(q, system, history=history):
                    full_text += chunk
                    yield _sse({"type": "delta", "content": chunk})
            except Exception as exc:
                error_msg = str(exc).strip() or type(exc).__name__
                if not full_text:
                    full_text = f"回答失败：{error_msg}"
                yield _sse({"type": "error", "content": f"（{error_msg}）"})

            # resume_advice 追加引导提示
            if route_type == "resume_advice":
                extra = "\n\n---\n💡 **提示**：前往「简历优化」页面上传简历，可获取完整的 AI 结构化分析和自动优化。"
                full_text += extra
                yield _sse({"type": "delta", "content": extra})

            # 保存 AI 消息
            await asyncio.to_thread(
                add_message, session_id, "assistant", full_text, route_type
            )

        elif route_type == "chart":
            # ===== 图表类：先提示，再一次性返回完整 JSON =====
            yield _sse({"type": "delta", "content": "正在生成图表..."})
            try:
                result = await asyncio.to_thread(agent._handle_chart, q, history)
                if result["type"] == "chart":
                    yield _sse({"type": "chart", "data": result["data"]})
                    await asyncio.to_thread(
                        add_message, session_id, "assistant", result["data"], "chart"
                    )
                else:
                    # 图表生成失败，返回文本
                    yield _sse({"type": "delta", "content": result["data"]})
                    await asyncio.to_thread(
                        add_message, session_id, "assistant", result["data"], "qa"
                    )
            except Exception as exc:
                error_msg = str(exc).strip() or type(exc).__name__
                yield _sse({"type": "error", "content": f"图表生成失败：{error_msg}"})
                await asyncio.to_thread(
                    add_message, session_id, "assistant", f"图表生成失败：{error_msg}", "error"
                )

        elif route_type == "job_search":
            # ===== 岗位搜索：上下文继承 + Redis 缓存 =====
            raw_keywords = agent._extract_job_keywords(q)
            if not raw_keywords or len(raw_keywords) < 2:
                msg = "请告诉我你想搜索什么岗位，例如：'搜索 Python 后端岗位'"
                yield _sse({"type": "delta", "content": msg})
                await asyncio.to_thread(add_message, session_id, "assistant", msg, "qa")
            else:
                # 1. 上下文继承：从 Redis 读取上次搜索关键词，补全当前查询
                prev_search = get_session_search(session_id) or {}
                prev_keywords = prev_search.get("keywords", "")
                prev_city = prev_search.get("city", "")
                keywords, city = agent._resolve_search_keywords(
                    raw_keywords, prev_keywords, prev_city
                )
                context_hint = ""
                if keywords != raw_keywords:
                    context_hint = f"（继承上下文：{raw_keywords} → {keywords}）"
                    yield _sse({
                        "type": "delta",
                        "content": f"检测到追问，自动补全搜索条件：{keywords} {context_hint}\n",
                    })

                # 2. 检查 Redis 缓存
                cached = get_cached_search(keywords, city)
                if cached is not None:
                    cards_json = json.dumps(cached, ensure_ascii=False)
                    yield _sse({
                        "type": "delta",
                        "content": f"⚡ 缓存命中，秒级返回「{keywords}」{len(cached)} 个岗位\n",
                    })
                    yield _sse({
                        "type": "job_search",
                        "data": cards_json,
                        "keywords": keywords,
                    })
                    await asyncio.to_thread(
                        add_message, session_id, "assistant", cards_json, "job_search", keywords
                    )
                    # 更新会话上下文
                    save_session_search(session_id, keywords, city)
                else:
                    yield _sse({"type": "delta", "content": f"正在搜索「{keywords}」相关岗位..."})
                    try:
                        from app.tools.jd_fetcher import NoSearchResultsError, fetch_search_page

                        cards = await fetch_search_page(keywords=keywords, city=city, max_results=10)
                        if not cards:
                            msg = f"未找到与「{keywords}」相关的岗位，请尝试其他关键词。"
                            yield _sse({"type": "delta", "content": msg})
                            await asyncio.to_thread(add_message, session_id, "assistant", msg, "qa")
                        else:
                            # 3. 写入 Redis 缓存
                            set_cached_search(keywords, city, cards)
                            cards_json = json.dumps(cards, ensure_ascii=False)
                            yield _sse({
                                "type": "job_search",
                                "data": cards_json,
                                "keywords": keywords,
                            })
                            await asyncio.to_thread(
                                add_message, session_id, "assistant", cards_json, "job_search", keywords
                            )
                        # 4. 更新会话上下文
                        save_session_search(session_id, keywords, city)
                    except NoSearchResultsError:
                        msg = f"未找到与「{keywords}」相关的岗位，请尝试其他关键词。"
                        yield _sse({"type": "delta", "content": msg})
                        await asyncio.to_thread(add_message, session_id, "assistant", msg, "qa")
                    except Exception as exc:
                        error_msg = str(exc).strip() or type(exc).__name__
                        yield _sse({"type": "error", "content": f"岗位搜索失败：{error_msg}"})
                        await asyncio.to_thread(
                            add_message, session_id, "assistant", f"搜索失败：{error_msg}", "error"
                        )

        # 7. 发送 end 事件
        yield _sse({"type": "end", "session_id": session_id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx 不缓冲
        },
    )


# ===== 会话管理路由 =====

class SessionListResponse(BaseModel):
    sessions: list[dict] = Field(default_factory=list)
    total: int = 0


@router.get("/sessions", response_model=SessionListResponse, summary="获取用户的会话列表")
async def get_sessions(user: CurrentUser) -> SessionListResponse:
    sessions = await asyncio.to_thread(list_user_sessions, user["id"])
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.get("/sessions/{session_id}/messages", summary="获取指定会话的所有消息")
async def get_messages(session_id: str, user: CurrentUser) -> dict:
    msgs = await asyncio.to_thread(get_session_messages, session_id)
    return {"session_id": session_id, "messages": msgs, "total": len(msgs)}


@router.delete("/sessions/{session_id}", summary="删除指定会话")
async def remove_session(session_id: str, user: CurrentUser) -> dict:
    await asyncio.to_thread(delete_session, session_id)
    return {"session_id": session_id, "deleted": True}


class SessionTitleUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


@router.patch("/sessions/{session_id}", summary="更新会话标题")
async def rename_session(session_id: str, payload: SessionTitleUpdate, user: CurrentUser) -> dict:
    await asyncio.to_thread(update_session_title, session_id, payload.title)
    return {"session_id": session_id, "title": payload.title}
