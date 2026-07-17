"""应用配置管理

使用 pydantic-settings 从环境变量 / .env 文件读取配置。
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，字段对应 .env 文件中的变量名。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===== 应用基础 =====
    APP_NAME: str = "FindJobAgent"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # ===== 数据库 =====
    # 格式: postgresql+asyncpg://用户名:密码@主机:端口/数据库名
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/findjobagent"

    # ===== JWT 认证（预留）=====
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 天

    # ===== CORS =====
    # 前端开发服务器地址，允许多个来源用逗号分隔
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    """获取配置单例，lru_cache 保证全局只读取一次 .env。"""
    return Settings()


settings = get_settings()
