"""FastAPI 公共依赖。"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.auth_service import AuthError, user_from_token

# 数据库会话依赖，路由参数中用 db: DBSession 即可注入
DBSession = Annotated[AsyncSession, Depends(get_db)]


# Bearer 令牌解析器；auto_error=False 表示缺少令牌时由我们返回自定义错误信息
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> dict:
    """从 Authorization: Bearer <令牌> 中解析当前登录用户。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或令牌缺失",
        )
    try:
        user = user_from_token(credentials.credentials)
    except AuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态已失效，请重新登录",
        ) from None
    return user.public_dict()


# 当前用户依赖，路由参数中用 user: CurrentUser 注入
CurrentUser = Annotated[dict, Depends(get_current_user)]
