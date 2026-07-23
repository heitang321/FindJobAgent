"""Redis 缓存客户端。

提供岗位搜索结果缓存和会话上下文存储。
当 Redis 不可用时自动降级，不影响主流程。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Any = None
_redis_checked: bool = False


def _get_redis() -> Any:
    """惰性初始化 Redis 连接，失败时返回 None。"""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True

    if not settings.REDIS_ENABLED:
        logger.info("Redis 缓存未启用（REDIS_ENABLED=False）")
        return None

    try:
        import redis

        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        _redis_client.ping()
        logger.info(
            "Redis 连接成功 %s:%s db=%s",
            settings.REDIS_HOST,
            settings.REDIS_PORT,
            settings.REDIS_DB,
        )
    except Exception as exc:
        logger.warning("Redis 连接失败，降级为无缓存模式: %s", exc)
        _redis_client = None

    return _redis_client


def cache_get(key: str) -> Any:
    """从 Redis 读取缓存值，返回反序列化后的对象。不可用时返回 None。"""
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis cache_get 失败 key=%s: %s", key, exc)
        return None


def cache_set(key: str, value: Any, ttl: int = 1800) -> bool:
    """写入 Redis 缓存，带 TTL。不可用时静默跳过。"""
    client = _get_redis()
    if client is None:
        return False
    try:
        client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        return True
    except Exception as exc:
        logger.warning("Redis cache_set 失败 key=%s: %s", key, exc)
        return False


def cache_delete(key: str) -> bool:
    """删除 Redis 缓存键。"""
    client = _get_redis()
    if client is None:
        return False
    try:
        client.delete(key)
        return True
    except Exception as exc:
        logger.warning("Redis cache_delete 失败 key=%s: %s", key, exc)
        return False


def is_available() -> bool:
    """Redis 是否可用。"""
    return _get_redis() is not None


# ===== 会话级上下文存储 =====

_SESSION_SEARCH_KEY_PREFIX = "chat:session:{session_id}:last_search"


def save_session_search(session_id: str, keywords: str, city: str = "") -> bool:
    """保存会话最近一次岗位搜索的关键词，供后续追问继承上下文。"""
    client = _get_redis()
    if client is None:
        return False
    key = _SESSION_SEARCH_KEY_PREFIX.format(session_id=session_id)
    return cache_set(key, {"keywords": keywords, "city": city}, ttl=3600)


def get_session_search(session_id: str) -> dict | None:
    """读取会话最近一次岗位搜索的关键词。"""
    client = _get_redis()
    if client is None:
        return None
    key = _SESSION_SEARCH_KEY_PREFIX.format(session_id=session_id)
    return cache_get(key)


# ===== 岗位搜索结果缓存 =====

_SEARCH_CACHE_KEY_PREFIX = "job_search:keywords:{keywords}:city:{city}"


def get_cached_search(keywords: str, city: str = "") -> list[dict] | None:
    """读取缓存的岗位搜索结果。"""
    client = _get_redis()
    if client is None:
        return None
    key = _SEARCH_CACHE_KEY_PREFIX.format(keywords=keywords, city=city)
    return cache_get(key)


def set_cached_search(
    keywords: str, city: str, cards: list[dict], ttl: int | None = None
) -> bool:
    """缓存岗位搜索结果。"""
    client = _get_redis()
    if client is None:
        return False
    key = _SEARCH_CACHE_KEY_PREFIX.format(keywords=keywords, city=city)
    return cache_set(key, cards, ttl or settings.JOB_SEARCH_CACHE_TTL)


# ===== JD 分析结果缓存 =====

_JD_CACHE_KEY_PREFIX = "jd_analysis:url:{url_hash}"


def get_cached_jd_analysis(jd_url: str) -> dict | None:
    """读取缓存的 JD 分析结果。"""
    client = _get_redis()
    if client is None:
        return None
    import hashlib

    url_hash = hashlib.md5(jd_url.encode()).hexdigest()
    key = _JD_CACHE_KEY_PREFIX.format(url_hash=url_hash)
    return cache_get(key)


def set_cached_jd_analysis(
    jd_url: str, result: dict, ttl: int | None = None
) -> bool:
    """缓存 JD 分析结果。"""
    client = _get_redis()
    if client is None:
        return False
    import hashlib

    url_hash = hashlib.md5(jd_url.encode()).hexdigest()
    key = _JD_CACHE_KEY_PREFIX.format(url_hash=url_hash)
    return cache_set(key, result, ttl or settings.JOB_SEARCH_CACHE_TTL)
