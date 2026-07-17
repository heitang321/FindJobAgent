"""认证接口（预留骨架）

后续在此实现注册、登录、获取当前用户信息等接口。
当前仅提供接口签名和响应模型，方便前端先联调。
"""
from fastapi import APIRouter

from app.api.deps import CurrentUser

router = APIRouter()


@router.get("/me", summary="获取当前用户信息")
async def get_me(user: CurrentUser) -> dict:
    """返回当前登录用户信息。

    接入 JWT 后从 token 中解析用户身份，
    目前依赖 deps.get_current_user 返回占位用户。
    """
    return user
