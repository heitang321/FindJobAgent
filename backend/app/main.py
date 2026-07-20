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

from app.api.v1.router import api_router
from app.core.config import settings


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


@app.get("/", tags=["root"])
async def root() -> dict:
    """根路径，重定向到 API 文档。"""
    return {"message": "FindJobAgent API", "docs": "/docs"}
