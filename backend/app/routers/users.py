"""用户路由：/api/users

列表 / 详情 / 画像（含购买与流失预测）/ 行为 / 订单 / 推荐（开发文档第 38 节 + 39.3 节）。
"""

from fastapi import APIRouter, Query

from ..core.exceptions import NotFoundError
from ..schemas.common import ApiResponse, ok
from ..services import user_service

router = APIRouter(tags=["users"])


@router.get("", response_model=ApiResponse[dict], summary="用户列表（分页/关键字）")
def list_users(
    keyword: str | None = Query(None, description="搜索 user_id / 城市"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ApiResponse[dict]:
    return ok(user_service.list_users(keyword=keyword, limit=limit, offset=offset))


@router.get("/{user_id}", response_model=ApiResponse[dict], summary="用户详情（基础信息 + 摘要）")
def get_user(user_id: str) -> ApiResponse[dict]:
    return ok(user_service.get_user(user_id))


@router.get("/{user_id}/profile", response_model=ApiResponse[dict], summary="用户画像 + 购买/流失概率")
def get_user_profile(user_id: str) -> ApiResponse[dict]:
    return ok(user_service.get_user_profile(user_id))


@router.get("/{user_id}/behaviors", response_model=ApiResponse[dict], summary="用户行为记录")
def get_user_behaviors(
    user_id: str,
    limit: int = Query(100, ge=1, le=500),
) -> ApiResponse[dict]:
    return ok(user_service.get_user_behaviors(user_id, limit=limit))


@router.get("/{user_id}/orders", response_model=ApiResponse[dict], summary="用户订单明细")
def get_user_orders(user_id: str) -> ApiResponse[dict]:
    return ok(user_service.get_user_orders(user_id))


@router.get("/{user_id}/recommendations", response_model=ApiResponse[dict], summary="用户推荐（默认 Popular）")
def get_user_recommendations(
    user_id: str,
    algorithm: str = Query("popular", description="popular/itemcf/usercf/content/hybrid"),
    top_k: int = Query(10, ge=1, le=50),
) -> ApiResponse[dict]:
    return ok(user_service.get_user_recommendations(user_id, algorithm=algorithm, top_k=top_k))


@router.get("/{user_id}/prediction", response_model=ApiResponse[dict], summary="用户购买/流失预测")
def get_user_prediction(user_id: str) -> ApiResponse[dict]:
    from ..services import prediction_service

    p = prediction_service.user_purchase(user_id)
    c = prediction_service.user_churn(user_id)
    if p is None and c is None:
        raise NotFoundError(message=f"用户不存在或无预测记录: {user_id}")
    return ok({"user_id": user_id, "purchase": p, "churn": c})