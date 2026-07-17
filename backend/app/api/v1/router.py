"""v1 路由聚合

将各业务路由模块统一注册到 v1 总路由，
main.py 中只需挂载一次 v1_router 即可。
"""
from fastapi import APIRouter

from app.api.v1 import auth, health

api_router = APIRouter()

# 各业务路由按模块注册，统一添加标签用于文档分组
api_router.include_router(health.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
