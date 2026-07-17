"""FastAPI 公共依赖。

认证相关依赖在此定义，后续接入 JWT 后只需实现 get_current_user。
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# 数据库会话依赖，路由参数中用 db: DBSession 即可注入
DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user() -> dict:
    """获取当前登录用户（预留）。

    后续接入 JWT 后实现逻辑：
    1. 从请求头 Authorization: Bearer <token> 解析 token
    2. 用 SECRET_KEY 解码，校验签名和过期时间
    3. 查询数据库返回用户对象

    目前返回占位用户，方便其他接口先开发。
    """
    # TODO: 接入 JWT 认证后替换为真实逻辑
    return {"id": 0, "username": "guest"}


# 当前用户依赖，路由参数中用 user: CurrentUser 注入
CurrentUser = Annotated[dict, Depends(get_current_user)]
