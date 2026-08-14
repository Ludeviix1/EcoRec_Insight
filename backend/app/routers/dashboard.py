"""Dashboard 路由：/api/dashboard/*

页面：总体 KPI、DAU 趋势、GMV 趋势、行为趋势、转化漏斗、留存/Cohort（开发文档第 39.1 节）。
"""

from fastapi import APIRouter, Query

from ..schemas.common import ApiResponse, ok
from ..services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/overview", response_model=ApiResponse[dict], summary="Dashboard 总体 KPI")
def overview() -> ApiResponse[dict]:
    return ok(dashboard_service.overview())


@router.get("/user-trend", response_model=ApiResponse[dict], summary="用户趋势（DAU/WAU/MAU/注册）")
def user_trend() -> ApiResponse[dict]:
    return ok(dashboard_service.user_trend())


@router.get("/gmv-trend", response_model=ApiResponse[dict], summary="GMV 趋势（日/周/月）")
def gmv_trend() -> ApiResponse[dict]:
    return ok(dashboard_service.gmv_trend())


@router.get("/behavior-trend", response_model=ApiResponse[dict], summary="用户行为趋势")
def behavior_trend() -> ApiResponse[dict]:
    return ok(dashboard_service.behavior_trend())


@router.get("/funnel", response_model=ApiResponse[dict], summary="转化漏斗")
def funnel() -> ApiResponse[dict]:
    return ok(dashboard_service.funnel())


@router.get("/retention", response_model=ApiResponse[dict], summary="留存 + Cohort 矩阵")
def retention() -> ApiResponse[dict]:
    return ok(dashboard_service.retention())


@router.get("/rankings", response_model=ApiResponse[dict], summary="商品/分类/品牌排行（Dashboard 用）")
def rankings(top_n: int = Query(10, ge=1, le=100)) -> ApiResponse[dict]:
    from ..services import item_service

    return ok(item_service.get_rankings(top_n=top_n))