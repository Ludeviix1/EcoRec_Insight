"""Item-CF 推荐（Phase 14，开发文档第 35.2 节）。

用户-商品矩阵权重：pv=1, click=2, collect=3, cart=4, buy=5（config.behavior_weights 可配）。
计算 item-item cosine similarity，流程：
    用户历史商品（种子） → item-item 相似商品 → 分数累加（种子权重 × 相似度）
    → 过滤（已购买/下架/不存在/重复） → Top-K

冷启动：新用户无历史 → 回退全局热门兜底。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse

from .base import BaseRecommender, minmax_01
from .config import RecommendConfig


class ItemCFRecommender(BaseRecommender):
    """基于 item-item 余弦相似度的协同过滤。"""

    name = "itemcf"

    def __init__(self, cfg: RecommendConfig | None = None):
        super().__init__(cfg)
        self._U: sparse.csr_matrix | None = None      # users × items 加权矩阵
        self._user_index: pd.Index | None = None
        self._item_index: pd.Index | None = None
        self._fallback: pd.Series | None = None       # 冷启动兜底（全局热门）

    def fit(self, behaviors: pd.DataFrame, items: pd.DataFrame,
            orders: pd.DataFrame | None = None, order_items: pd.DataFrame | None = None,
            ref_date: pd.Timestamp | None = None) -> "ItemCFRecommender":
        """构建用户-商品加权矩阵（行为权重，pv=1..buy=5）。"""
        self.load_context(items, orders, order_items)

        beh = behaviors[["user_id", "item_id", "behavior_type"]].copy()
        beh["user_id"] = beh["user_id"].astype(str)
        beh["item_id"] = beh["item_id"].astype(str)
        beh["w"] = beh["behavior_type"].map(self.cfg.behavior_weights).fillna(0.0)

        users = pd.Index(sorted(beh["user_id"].unique()))
        items_idx = pd.Index(sorted(items["item_id"].astype(str).unique()))
        self._user_index = users
        self._item_index = items_idx

        # 聚合重复 (user, item) 后建稀疏矩阵
        agg = beh.groupby(["user_id", "item_id"], sort=False)["w"].sum()
        ui_user = np.array([users.get_loc(u) for u in agg.index.get_level_values(0)])
        ui_item = np.array([items_idx.get_loc(i) for i in agg.index.get_level_values(1)])
        self._U = sparse.csr_matrix((agg.to_numpy(), (ui_user, ui_item)),
                                     shape=(len(users), len(items_idx))).tocsr().astype(np.float32)

        # 兜底热门：商品总分（行为加权）min-max 到 [0,1]
        total = agg.groupby("item_id").sum()
        self._fallback = minmax_01(total)
        if ref_date is not None:
            self.ref_date = pd.Timestamp(ref_date).normalize()
        return self

    def _seed_for(self, user_id: str) -> pd.Series:
        """用户在该 user-item 矩阵上的非零种子（item_id -> 权重）。"""
        if self._U is None or self._user_index is None:
            raise RuntimeError("请先调用 fit()")
        if str(user_id) not in self._user_index:
            return pd.Series(dtype=float)      # 未知用户 → 空种子（走冷启动兜底）
        ui = self._user_index.get_loc(str(user_id))
        row = self._U.getrow(ui)
        return pd.Series(row.data, index=self._item_index[row.indices])

    def score_candidates(self, user_id: str, candidates: pd.Index) -> pd.Series:
        """返回候选商品 Item-CF 分数（未过滤，供 Hybrid 融合）。

        score(cand) = Σ_种子 Σ_历史种子权重 × cos(种子, cand)
        """
        seeds = self._seed_for(user_id)
        if len(seeds) == 0 or len(candidates) == 0:
            fall = self._fallback
            if fall is None:
                return pd.Series(0.0, index=candidates)
            return fall.reindex(candidates).fillna(0.0)

        tree = self._item_index.get_indexer(candidates)
        cols = self._item_index.get_indexer(seeds.index)
        Us = self._U[:, cols]
        Uc = self._U[:, tree]
        sim = Us.T @ Uc                        # n_seed × n_cand（user 维度点积）
        sim = sim.toarray().astype(np.float64)

        # 余弦归一化
        sn = np.asarray(Us.power(2).sum(axis=0)).ravel() ** 0.5
        cn = (np.asarray(Uc.power(2).sum(axis=0)).ravel() + 1e-9) ** 0.5
        with np.errstate(divide="ignore", invalid="ignore"):
            cos = sim / np.outer(sn, cn)
        cos = np.nan_to_num(cos)

        seed_w = seeds.to_numpy()
        score = cos.T @ seed_w                # n_cand
        out = pd.Series(score, index=candidates)
        return out

    def _rank(self, user_id: str, candidates: pd.Index, top_k: int) -> pd.DataFrame:
        score = self.score_candidates(user_id, candidates).sort_values(ascending=False)
        ranked = score.head(top_k).copy().reset_index()
        ranked.columns = ["item_id", "score"]
        ranked["reason"] = "物品协同：与你历史浏览/购买过的商品经常被一起浏览或购买（商品间相似）"
        ranked["score"] = ranked["score"].round(4)
        return ranked[["item_id", "score", "reason"]]