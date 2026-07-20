"""数据库连接管理

使用 SQLAlchemy 2.0 异风格式 + asyncpg 驱动连接 PostgreSQL。
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# create_async_engine 创建异步引擎
# pool_pre_ping: 连接前检测是否存活，避免使用已断开的连接
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # DEBUG 模式打印 SQL
    pool_pre_ping=True,
)

# async_sessionmaker 是异步会话工厂，每次调用生成一个独立会话
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 后对象仍可访问，避免异步懒加载报错
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖注入：为每个请求提供一个数据库会话。

    用法（路由参数）:
        @router.get("/")
        async def index(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
