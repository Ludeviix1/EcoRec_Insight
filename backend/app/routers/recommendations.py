"""推荐路由：/api/recommendations/*

单算法推荐 / 多算法对比 / 推荐评估（开发文档第 38 / 39.5 节）。
"""

from fastapi import APIRouter, Query

from ..schemas.common import ApiResponse, ok
from ..services import recommendation_service

router = APIRouter(tags=["recommendations"])


@router.get("/metrics", response_model=ApiResponse[dict], summary="推荐评估（5 算法离线指标 + 权重实验）")
def metrics() -> ApiResponse[dict]:
    return ok(recommendation_service.metrics())


@router.get("/{user_id}/compare", response_model=ApiResponse[dict], summary="多算法推荐对比")
def compare(
    user_id: str,
    algorithms: str | None = Query(None, description="逗号分隔算法，默认全部 5 种"),
    top_k: int = Query(10, ge=1, le=50),
) -> ApiResponse[dict]:
    algos = [a.strip().lower() for a in algorithms.split(",") if a.strip()] if algorithms else None
    return ok(recommendation_service.compare(user_id, algorithms=algos, top_k=top_k))


@router.get("/{user_id}", response_model=ApiResponse[dict], summary="获取某用户推荐")
def recommend_for_user(
    user_id: str,
    algorithm: str = Query("popular", description="popular/itemcf/usercf/content/hybrid"),
    top_k: int = Query(10, ge=1, le=50),
) -> ApiResponse[dict]:
    return ok(recommendation_service.recommend(user_id, algorithm=algorithm, top_k=top_k))