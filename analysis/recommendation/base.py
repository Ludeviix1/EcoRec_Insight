"""推荐系统基类与公共工具（开发文档第 35 节）。

统一接口（开发文档第 35 节）：
    recommend(user_id: str, top_k: int = 10) -> list[dict]

公共能力：
- 行为时间衰减（half-life 指数衰减）；
- min-max 标准化到 [0,1]；
- 过滤：已购买 / 已下架 / 不存在 / 重复（开发文档第 35.7 节）。

所有推荐器必须继承 ``BaseRecommender`` 并实现 ``_rank``；``recommend`` 负责
过滤与 Top-K，保证口径一致。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from analysis.analysis.base import BEHAVIOR_TYPES

from .config import RecommendConfig


def time_decay_weight(event_dates: pd.Series, ref_date: pd.Timestamp, half_life: float) -> pd.Series:
    """指数时间衰减：decay = 0.5 ** ((ref_date - event_date).days / half_life)。

    - 行为越接近 ref_date 权重越接近 1；越早越趋近 0；
    - half_life=0 表示不做衰减（恒为 1）。
    """
    if half_life <= 0:
        return pd.Series(1.0, index=event_dates.index)
    days = (ref_date - pd.to_datetime(event_dates, errors="coerce").dt.normalize()).dt.days
    days = days.clip(lower=0)
    return np.power(0.5, days / float(half_life))


def minmax_01(s: pd.Series) -> pd.Series:
    """min-max 标准化到 [0,1]；全 0 或单值时返回 0。"""
    mn, mx = s.min(), s.max()
    if mx <= mn:
        return pd.Series(0.0, index=s.index)
    return (s - mn) / (mx - mn)


def weighted_behavior_score(
    behaviors: pd.DataFrame,
    cfg: RecommendConfig,
    ref_date: pd.Timestamp,
) -> pd.Series:
    """按 商品 x 行为类型 加权（含时间衰减）聚合，返回各商品的行为加权分。

    公式（开发文档第 49.9 节）：
        raw_score(item) = Σ_b w_b * Σ_events(decay(event))
    返回一个以 item_id 为索引的 Series（原始分数，未标准化）。
    """
    beh = behaviors[["item_id", "behavior_type", "event_date"]].copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh["decay"] = time_decay_weight(beh["event_date"], ref_date, cfg.half_life_days).to_numpy()
    beh["weight"] = beh["behavior_type"].map(cfg.behavior_weights).fillna(0.0)
    beh["weighted"] = beh["weight"] * beh["decay"]

    raw = beh.groupby("item_id")["weighted"].sum()
    raw = raw[raw > 0]
    return raw


class BaseRecommender(ABC):
    """推荐器基类：统一过滤 + Top-K 接口。"""

    name: str = "base"

    def __init__(self, cfg: RecommendConfig | None = None):
        self.cfg = cfg or RecommendConfig()
        self._items: pd.DataFrame | None = None     # items 维度（item_id 索引）
        self._purchased: dict[str, set[str]] = {}   # user_id -> 已购买 item_id 集合

    # ---- 数据装配 ----
    def load_context(
        self,
        items: pd.DataFrame,
        orders: pd.DataFrame | None = None,
        order_items: pd.DataFrame | None = None,
    ) -> None:
        """装配商品维度与"已购买"映射（推荐过滤用）。"""
        dim = items.copy()
        dim["item_id"] = dim["item_id"].astype(str)
        self._items = dim.set_index("item_id")

        purchased: dict[str, set[str]] = {}
        if orders is not None and order_items is not None:
            paid = orders.loc[orders["status"] == "paid", ["order_id", "user_id"]].copy()
            oi = order_items[["order_id", "item_id"]].merge(paid, on="order_id", how="inner")
            oi["item_id"] = oi["item_id"].astype(str)
            oi["user_id"] = oi["user_id"].astype(str)
            for uid, g in oi.groupby("user_id"):
                purchased[str(uid)] = set(g["item_id"])
        self._purchased = purchased

    # ---- 过滤 ----
    def _candidate_items(self, user_id: str) -> pd.Index:
        """返回候选商品 item_id（去除已购买 / 已下架 / 不存在 / 重复）。"""
        if self._items is None:
            raise RuntimeError("请先调用 load_context() 装配商品与订单上下文")
        cand = self._items.index

        if self.cfg.filter_off_shelf and "status" in self._items.columns:
            cand = cand[self._items.loc[cand, "status"].astype(int) == 1]

        if self.cfg.filter_purchased:
            bought = self._purchased.get(str(user_id), set())
            if bought:
                cand = cand[~cand.isin(bought)]

        return cand.drop_duplicates()

    # ---- 子类实现 ----
    @abstractmethod
    def _rank(self, user_id: str, candidates: pd.Index, top_k: int) -> pd.DataFrame:
        """对候选商品打分并返回前 top_k 行，列含 item_id / score / reason。"""

    # ---- 统一入口 ----
    def recommend(self, user_id: str, top_k: int = 10) -> list[dict]:
        """返回 Top-K 推荐列表：[{item_id, item_name, category_id, brand, price, score, reason}]。"""
        candidates = self._candidate_items(user_id)
        if len(candidates) == 0:
            return []
        ranked = self._rank(str(user_id), candidates, top_k)
        if self._items is None:
            return []
        dim = self._items
        out = []
        for r in ranked.itertuples():
            row = {
                "item_id": r.item_id,
                "item_name": str(dim.loc[r.item_id, "item_name"]) if "item_name" in dim.columns else "",
                "category_id": str(dim.loc[r.item_id, "category_id"]) if "category_id" in dim.columns else "",
                "brand": (str(dim.loc[r.item_id, "brand"]) if pd.notna(dim.loc[r.item_id, "brand"]) else ""),
                "price": round(float(dim.loc[r.item_id, "price"]), 2) if "price" in dim.columns else None,
                "score": round(float(r.score), 4),
                "reason": r.reason,
            }
            out.append(row)
        return out