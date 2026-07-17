"""健康检查接口

用于运维监控和前端连接探测，不依赖数据库。
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health_check() -> dict:
    """返回服务状态，供前端探活和运维监控使用。"""
    return {"status": "ok", "service": "FindJobAgent API"}
