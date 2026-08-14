"""深度分析路由：/api/analysis/*

RFM / 生命周期 / Cohort / 购买路径 / 渠道 / 价格 / 关联规则 / 分群 / 设备 / 业务发现。
"""

from fastapi import APIRouter

from ..schemas.common import ApiResponse, ok
from ..services import analysis_service

router = APIRouter(tags=["analysis"])


@router.get("/rfm", response_model=ApiResponse[dict], summary="RFM 用户价值分群")
def rfm() -> ApiResponse[dict]:
    return ok(analysis_service.rfm())


@router.get("/lifecycle", response_model=ApiResponse[dict], summary="用户生命周期")
def lifecycle() -> ApiResponse[dict]:
    return ok(analysis_service.lifecycle())


@router.get("/cohort", response_model=ApiResponse[dict], summary="Cohort 留存矩阵")
def cohort() -> ApiResponse[dict]:
    return ok(analysis_service.cohort())


@router.get("/path", response_model=ApiResponse[dict], summary="用户购买路径")
def path() -> ApiResponse[dict]:
    return ok(analysis_service.path())


@router.get("/channel", response_model=ApiResponse[dict], summary="渠道质量对比")
def channel() -> ApiResponse[dict]:
    return ok(analysis_service.channel())


@router.get("/price", response_model=ApiResponse[dict], summary="价格分析")
def price() -> ApiResponse[dict]:
    return ok(analysis_service.price())


@router.get("/association", response_model=ApiResponse[dict], summary="商品关联规则")
def association() -> ApiResponse[dict]:
    return ok(analysis_service.association())


@router.get("/segments", response_model=ApiResponse[dict], summary="KMeans 用户分群")
def segments() -> ApiResponse[dict]:
    return ok(analysis_service.segments())


@router.get("/device", response_model=ApiResponse[dict], summary="设备分析")
def device() -> ApiResponse[dict]:
    return ok(analysis_service.device())


@router.get("/findings", response_model=ApiResponse[dict], summary="业务发现（现象→证据→原因→建议）")
def findings() -> ApiResponse[dict]:
    return ok(analysis_service.findings())


@router.get("/meta", response_model=ApiResponse[dict], summary="分析运行记录")
def meta() -> ApiResponse[dict]:
    return ok(analysis_service.meta())