"""深度分析服务：RFM / 生命周期 / Cohort / 购买路径 / 渠道 / 价格 / 关联 / 分群等。

直接透传 data/analysis 离线分析产物（开发文档 API 分层：Service → Repository）。
"""

from __future__ import annotations

from ..core.exceptions import NotFoundError
from ..repositories import analysis_repo


def get(name: str) -> dict:
    try:
        return analysis_repo.get_item(name)
    except NotFoundError:
        raise NotFoundError(message=f"未知分析指标: {name}")


def rfm() -> dict:
    return analysis_repo.get_item("rfm")


def lifecycle() -> dict:
    return analysis_repo.get_item("lifecycle")


def cohort() -> dict:
    return analysis_repo.get_item("cohort")


def path() -> dict:
    return analysis_repo.get_item("path")


def channel() -> dict:
    return analysis_repo.get_item("channel")


def price() -> dict:
    return analysis_repo.get_item("price")


def association() -> dict:
    return analysis_repo.get_item("association")


def segments() -> dict:
    return analysis_repo.get_item("segments")


def findings() -> dict:
    return analysis_repo.get_item("findings")


def device() -> dict:
    return analysis_repo.get_item("device")


def meta() -> dict:
    from ..repositories.base import ANALYSIS_DIR, read_json

    return read_json(ANALYSIS_DIR, "analysis_meta")