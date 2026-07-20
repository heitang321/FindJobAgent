"""FindJobAgent 后端入口

启动方式:
    uvicorn app.main:app --reload --port 8000

启动后访问:
    API 文档: http://localhost:8000/docs
    健康检查: http://localhost:8000/api/v1/health
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import engine
from app.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。

    startup 阶段做资源初始化（如建表、连接池预热），
    shutdown 阶段做资源清理。

    目前仅做日志提示，后续可在此初始化数据库表、
    连接 Redis、启动定时任务等。
    """
    # ===== startup =====
    print(f"[{settings.APP_NAME}] 启动中...")
    # 建表（如果表不存在）
    Base.metadata.create_all(bind=engine)
    # 自动迁移：补齐已有表中缺失的 updated_at 列
    _ensure_updated_at_columns()
    _ensure_resume_task_columns()
    print(f"[{settings.APP_NAME}] 数据库表已就绪")
    yield
    # ===== shutdown =====
    print(f"[{settings.APP_NAME}] 正在关闭...")


app = FastAPI(
    title=settings.APP_NAME,
    description="简历优化智能助手后端 API",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# ===== 中间件 =====
# CORS：允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 路由注册 =====
# 所有 v1 接口统一挂在 /api/v1 前缀下
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


def _ensure_updated_at_columns() -> None:
    """检查已有表是否缺少 updated_at 列，若缺少则自动 ALTER TABLE 补齐。

    用户通过 job_agent.sql 建表时，部分表可能只有 created_at 而无 updated_at。
    Base.metadata.create_all 不会修改已存在的表，因此需要手动迁移。
    """
    inspector = inspect(engine)
    # 所有继承 Base 的表名
    target_tables = {t for t in Base.metadata.tables}
    for table_name in target_tables:
        if table_name not in inspector.get_table_names():
            continue
        columns = {c["name"] for c in inspector.get_columns(table_name)}
        if "updated_at" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE `{table_name}` "
                        f"ADD COLUMN `updated_at` DATETIME "
                        f"DEFAULT CURRENT_TIMESTAMP "
                        f"ON UPDATE CURRENT_TIMESTAMP"
                    )
                )
            print(f"  [迁移] 已为表 `{table_name}` 添加 `updated_at` 列")


def _ensure_resume_task_columns() -> None:
    """补齐岗位搜索合并后新增的 resume_tasks 字段。"""
    table_name = "resume_tasks"
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(table_name)}
    required = {
        "jd_url": "TEXT NULL",
        "job_search_results": "JSON NULL",
        "selected_jd_url": "TEXT NULL",
    }
    for column_name, column_type in required.items():
        if column_name in existing:
            continue
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE `{table_name}` "
                    f"ADD COLUMN `{column_name}` {column_type}"
                )
            )
        print(f"  [迁移] 已为表 `{table_name}` 添加 `{column_name}` 列")


@app.get("/", tags=["root"])
async def root() -> dict:
    """根路径，重定向到 API 文档。"""
    return {"message": "FindJobAgent API", "docs": "/docs"}
