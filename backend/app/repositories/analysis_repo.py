"""分析与画像仓库：读取 data/analysis/*.json 离线分析产物。

覆盖：用户规模、DAU/WAU/MAU、行为、活跃时间、GMV、排行、漏斗、留存/Cohort/RFM、
生命周期、路径、商品生命周期、价格、渠道、设备、关联规则、分群、画像、业务发现。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..core.exceptions import NotFoundError
from .base import ANALYSIS_DIR, ANALYSIS_FILE_MAP, ANALYSIS_NAMES, read_json


def get_item(name: str) -> dict:
    """按端点名读取分析 JSON（name 走 ANALYSIS_FILE_MAP 归一化）。"""
    key = name.strip().lower()
    fname = ANALYSIS_FILE_MAP.get(key, key)
    if fname not in ANALYSIS_NAMES:
        raise NotFoundError(message=f"未知分析指标: {name}")
    return read_json(ANALYSIS_DIR, fname)


def list_names() -> list[str]:
    return list(ANALYSIS_NAMES)


@lru_cache(maxsize=1)
def _user_profile_index() -> dict[str, dict]:
    data = read_json(ANALYSIS_DIR, "user_profile")
    return {p["user_id"]: p for p in data.get("profiles", [])}


@lru_cache(maxsize=1)
def _item_profile_index() -> dict[str, dict]:
    data = read_json(ANALYSIS_DIR, "item_profile")
    return {p["item_id"]: p for p in data.get("profiles", [])}


def user_profile(user_id: str) -> dict[Any, Any]:
    profiles = _user_profile_index()
    p = profiles.get(str(user_id))
    if p is None:
        raise NotFoundError(message=f"用户不存在: {user_id}")
    return p


def item_profile(item_id: str) -> dict[Any, Any]:
    profiles = _item_profile_index()
    p = profiles.get(str(item_id))
    if p is None:
        raise NotFoundError(message=f"商品不存在: {item_id}")
    return p