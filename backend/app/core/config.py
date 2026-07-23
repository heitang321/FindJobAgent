"""应用配置管理。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """从项目根目录或 backend/.env 读取配置。"""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 应用基础
    APP_NAME: str = "FindJobAgent"
    DEBUG: bool = True
    TESTING: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # MySQL 持久化。也可以通过 DATABASE_URL 覆盖完整同步连接地址。
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DB: str = "job_agent"
    DATABASE_URL: str = ""

    # Redis 缓存（岗位搜索结果缓存 + 会话上下文）
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_ENABLED: bool = False  # 未配置时降级跳过缓存
    JOB_SEARCH_CACHE_TTL: int = 1800  # 岗位搜索缓存 30 分钟

    # JWT 认证
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # 登录注册 / 邮箱验证码
    AUTH_LOCAL_USER_STORE: str = "data/auth_users.json"
    AUTH_VERIFICATION_EXPIRE_SECONDS: int = 300
    AUTH_VERIFICATION_RESEND_SECONDS: int = 60
    AUTH_VERIFICATION_CODE_LENGTH: int = 6
    AUTH_EMAIL_SEND_ENABLED: bool = True
    AUTH_DEBUG_RETURN_CODE: bool = False
    EMAIL_HOST: str = "smtp.qq.com"
    EMAIL_PORT: int = 465
    EMAIL_FROM: str = ""
    EMAIL_PASSWORD: str = ""

    # 简历上传
    RESUME_UPLOAD_DIR: str = "uploads/resumes"
    RESUME_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024

    # AI 模型（OpenAI 兼容接口）
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_MODEL: str = ""
    AI_ANALYSIS_ENABLED: bool = True
    AI_TIMEOUT_SECONDS: int = 60
    AI_TEMPERATURE: float = 0.2

    # Agent 3
    OPTIMIZATION_OUTPUT_DIR: str = "outputs/optimized_resumes"
    OPTIMIZATION_MAX_WORKERS: int = 4

    # 招聘网站抓取白名单
    JOB_ALLOWED_HOSTS: list[str] = ["zhaopin.com"]

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    """获取配置单例并补齐默认 MySQL 同步连接地址。"""
    configured = Settings()
    if not configured.DATABASE_URL:
        user = quote_plus(configured.MYSQL_USER)
        password = quote_plus(configured.MYSQL_PASSWORD)
        configured.DATABASE_URL = (
            f"mysql+pymysql://{user}:{password}"
            f"@{configured.MYSQL_HOST}:{configured.MYSQL_PORT}/{configured.MYSQL_DB}"
            "?charset=utf8mb4"
        )
    return configured


settings = get_settings()
