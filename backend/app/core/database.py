"""数据库连接管理

使用 SQLAlchemy 2.0 同步风格 + pymysql 驱动连接 MySQL。
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# create_engine 创建同步引擎
# pool_pre_ping: 连接前检测是否存活，避免使用已断开的连接
# pool_recycle: 每 8 小时回收连接，避免 MySQL wait_timeout 断连
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # DEBUG 模式打印 SQL
    pool_pre_ping=True,
    pool_recycle=28800,
    pool_size=10,
    max_overflow=20,
)

# sessionmaker 是同步会话工厂，每次调用生成一个独立会话
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,  # commit 后对象仍可访问
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖注入：为每个请求提供一个数据库会话。

    用法（路由参数）:
        @router.get("/")
        def index(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
