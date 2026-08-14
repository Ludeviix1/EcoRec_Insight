"""User-CF 推荐（Phase 14，开发文档第 35.3 节）。

构建 user-user similarity（余弦），流程：
    目标用户 → 相似用户（Top-N）→ 相似用户喜欢的商品 → 过滤 → 加权（相似度×行为权重）
    → Top-K

冷启动：新用户无历史（无法计算相似用户）→ 回退全局热门兜底。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse

from .base import BaseRecommender, minmax_01
from .config import RecommendConfig

DEFAULT_N_NEIGHBORS = 50   # 目标用户取前 N 个相似用户


class UserCFRecommender(BaseRecommender):
    """基于 user-user 余弦相似度的协同过滤。"""

    name = "usercf"

    def __init__(self, cfg: RecommendConfig | None = None, n_neighbors: int | None = None):
        super().__init__(cfg)
        self._U: sparse.csr_matrix | None = None      # users × items 加权矩阵
        self._user_index: pd.Index | None = None
        self._item_index: pd.Index | None = None
        self._user_norm: np.ndarray | None = None     # 每用户 L2 范数（加速余弦）
        self._fallback: pd.Series | None = None
        self.n_neighbors = n_neighbors or DEFAULT_N_NEIGHBORS

    def fit(self, behaviors: pd.DataFrame, items: pd.DataFrame,
            orders: pd.DataFrame | None = None, order_items: pd.DataFrame | None = None,
            ref_date: pd.Timestamp | None = None) -> "UserCFRecommender":
        """构建用户-商品加权矩阵并预计算用户范数。"""
        self.load_context(items, orders, order_items)

        beh = behaviors[["user_id", "item_id", "behavior_type"]].copy()
        beh["user_id"] = beh["user_id"].astype(str)
        beh["item_id"] = beh["item_id"].astype(str)
        beh["w"] = beh["behavior_type"].map(self.cfg.behavior_weights).fillna(0.0)

        users = pd.Index(sorted(beh["user_id"].unique()))
        items_idx = pd.Index(sorted(items["item_id"].astype(str).unique()))
        self._user_index = users
        self._item_index = items_idx

        agg = beh.groupby(["user_id", "item_id"], sort=False)["w"].sum()
        ui_user = np.array([users.get_loc(u) for u in agg.index.get_level_values(0)])
        ui_item = np.array([items_idx.get_loc(i) for i in agg.index.get_level_values(1)])
        self._U = sparse.csr_matrix((agg.to_numpy(), (ui_user, ui_item)),
                                     shape=(len(users), len(items_idx))).tocsr().astype(np.float32)
        self._user_norm = np.asarray(self._U.power(2).sum(axis=1)).ravel() ** 0.5

        total = agg.groupby("item_id").sum()
        self._fallback = minmax_01(total)
        if ref_date is not None:
            self.ref_date = pd.Timestamp(ref_date).normalize()
        return self

    def _similar_users(self, user_id: str, n: int) -> pd.Series:
        """目标用户与所有其他用户的余弦相似度，返回 Top-N（不含自身）。"""
        if self._U is None or self._user_index is None:
            raise RuntimeError("请先调用 fit()")
        if str(user_id) not in self._user_index:
            return pd.Series(dtype=float)      # 未知用户 → 无相似用户
        ui = self._user_index.get_loc(str(user_id))
        row = self._U.getrow(ui)
        dots = (row @ self._U.T).toarray().ravel()     # 与所有用户的点积
        norm = self._user_norm[ui]
        sim = dots / (norm * self._user_norm + 1e-9)
        sim[ui] = -1.0                                  # 排除自身
        idx = np.argsort(-sim)[:n]
        return pd.Series(sim[idx], index=self._user_index[idx])

    def score_candidates(self, user_id: str, candidates: pd.Index) -> pd.Series:
        """候选商品 User-CF 分数（未过滤，供 Hybrid 融合）。

        score(cand) = Σ_相似用户 sim(user, u) × w(u, cand)
        """
        if str(user_id) not in set(self._user_index):
            fall = self._fallback
            if fall is None:
                return pd.Series(0.0, index=candidates)
            return fall.reindex(candidates).fillna(0.0)

        neighbors = self._similar_users(user_id, self.n_neighbors)
        if len(neighbors) == 0 or len(candidates) == 0:
            fall = self._fallback
            return fall.reindex(candidates).fillna(0.0) if fall is not None else pd.Series(0.0, index=candidates)

        nrows = self._U[list(self._user_index.get_loc(u) for u in neighbors.index)]
        # 取候选列
        cols = self._item_index.get_indexer(candidates)
        sub = nrows[:, cols].toarray().astype(np.float64)
        sim_w = neighbors.to_numpy()
        score = sub.T @ sim_w                          # n_cand
        return pd.Series(score, index=candidates)

    def _rank(self, user_id: str, candidates: pd.Index, top_k: int) -> pd.DataFrame:
        score = self.score_candidates(user_id, candidates).sort_values(ascending=False)
        ranked = score.head(top_k).copy().reset_index()
        ranked.columns = ["item_id", "score"]
        ranked["reason"] = "User-CF：与你偏好相似的用户喜欢的商品"
        ranked["score"] = ranked["score"].round(4)
        return ranked[["item_id", "score", "reason"]]