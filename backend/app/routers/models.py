"""预测模型路由：/api/models/*

购买预测 / 流失预测 / 模型评估汇总 + 推荐评估（开发文档第 38 / 39.6 节）。
"""

from fastapi import APIRouter, Query

from ..schemas.common import ApiResponse, ok
from ..services import prediction_service

router = APIRouter(tags=["models"])


@router.get("/purchase", response_model=ApiResponse[dict], summary="购买预测模型详情")
def purchase() -> ApiResponse[dict]:
    return ok(prediction_service.purchase())


@router.get("/churn", response_model=ApiResponse[dict], summary="流失预测模型 + 高风险用户列表")
def churn(limit: int = Query(50, ge=1, le=200)) -> ApiResponse[dict]:
    return ok(prediction_service.churn(limit=limit))


@router.get("/metrics", response_model=ApiResponse[dict], summary="预测 + 推荐评估指标汇总")
def metrics() -> ApiResponse[dict]:
    return ok(prediction_service.metrics())