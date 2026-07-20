"""应用配置管理

使用 pydantic-settings 从环境变量 / .env 文件读取配置。
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """应用配置，字段对应 .env 文件中的变量名。"""

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===== 应用基础 =====
    APP_NAME: str = "FindJobAgent"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # ===== 数据库 (MySQL) =====
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DB: str = "job_agent"
    # 自动拼接同步连接 URL: mysql+pymysql://user:pass@host:port/db
    DATABASE_URL: str = ""

    # ===== JWT 认证（预留）=====
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 天

    # ===== 登录注册 / 邮箱验证码 =====
    AUTH_VERIFICATION_EXPIRE_SECONDS: int = 300
    AUTH_VERIFICATION_RESEND_SECONDS: int = 60
    AUTH_VERIFICATION_CODE_LENGTH: int = 6
    AUTH_EMAIL_SEND_ENABLED: bool = True
    AUTH_DEBUG_RETURN_CODE: bool = False
    EMAIL_HOST: str = "smtp.qq.com"
    EMAIL_PORT: int = 465
    EMAIL_FROM: str = ""
    EMAIL_PASSWORD: str = ""

    # ===== 简历上传 =====
    # 上传文件的存储目录（相对于 backend 目录）
    RESUME_UPLOAD_DIR: str = "uploads/resumes"

    # ===== AI 模型（OpenAI 兼容接口）=====
    # 例如 DeepSeek: AI_BASE_URL=https://api.deepseek.com/v1, AI_MODEL=deepseek-chat
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_MODEL: str = ""
    AI_ANALYSIS_ENABLED: bool = True
    AI_TIMEOUT_SECONDS: int = 60
    AI_TEMPERATURE: float = 0.2

    # ===== Agent 3 简历优化 =====
    OPTIMIZATION_OUTPUT_DIR: str = "outputs/optimized_resumes"
    OPTIMIZATION_MAX_WORKERS: int = 4

    # ===== CORS =====
    # 前端开发服务器地址，允许多个来源用逗号分隔
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """获取配置单例，lru_cache 保证全局只读取一次 .env。"""
    s = Settings()
    # 如果未显式配置 DATABASE_URL，则从 MYSQL_* 字段自动拼接
    if not s.DATABASE_URL:
        s.DATABASE_URL = (
            f"mysql+pymysql://{s.MYSQL_USER}:{s.MYSQL_PASSWORD}"
            f"@{s.MYSQL_HOST}:{s.MYSQL_PORT}/{s.MYSQL_DB}"
            "?charset=utf8mb4"
        )
    return s


settings = get_settings()
