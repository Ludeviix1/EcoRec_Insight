"""健康检查路由：GET /api/health

返回：{"code": 0, "message": "success", "data": {"status": "ok"}}
"""

from fastapi import APIRouter

from ..schemas.common import ApiResponse, ok

router = APIRouter(tags=["system"])


@router.get("/health", response_model=ApiResponse[dict], summary="服务健康检查")
def health() -> ApiResponse[dict]:
    return ok({"status": "ok"})