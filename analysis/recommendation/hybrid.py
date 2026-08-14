"""Hybrid 推荐（Phase 14，开发文档第 49.12 节 / 35.5 节）。

统一 4 路召回并分数归一化后加权融合：

    HybridScore = w1*ItemCF + w2*UserCF + w3*Popular + w4*Content

要求（开发文档第 49.12 节）：
    - 权重可配置（HYBRID_WEIGHTS）；
    - 至少做 baseline vs hybrid 对比；
    - 最终结论必须基于评估指标（由 scripts/run_hybrid.py 完成离线对比）。

融合口径（开发文档第 35.5 节）：候选商品在每路算法上先归一化到 [0,1]，
再按权重线性融合，保证各分量在同一个量纲上。
"""

from __future__ import annotations

import pandas as pd

from .base import BaseRecommender, minmax_01
from .config import RecommendConfig
from .content import ContentRecommender
from .itemcf import ItemCFRecommender
from .popular import PopularRecommender
from .usercf import UserCFRecommender

DEFAULT_HYBRID_WEIGHTS: dict[str, float] = {
    "itemcf": 0.25, "usercf": 0.15, "popular": 0.30, "content": 0.30,
}

_HYBRID_ORDER = ("itemcf", "usercf", "popular", "content")


def _parse_hybrid_weights(raw: str) -> dict[str, float]:
    """解析混合权重，支持 JSON 或 key:v,key:v 形式。"""
    import json
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return {k: float(v) for k, v in json.loads(raw).items()}
        except Exception:
            pass
    out: dict[str, float] = {}
    for item in raw.split(","):
        if ":" in item:
            k, v = item.split(":", 1)
            out[k.strip()] = float(v.strip())
    return out


class HybridRecommender(BaseRecommender):
    """ItemCF/UserCF/Popular/Content 分数归一化后加权融合。"""

    name = "hybrid"

    def __init__(self, cfg: RecommendConfig | None = None,
                 hybrid_weights: dict[str, float] | None = None,
                 n_neighbors: int | None = None):
        super().__init__(cfg)
        self.hybrid_weights = hybrid_weights or dict(DEFAULT_HYBRID_WEIGHTS)
        self._itemcf = ItemCFRecommender(self.cfg)
        self._usercf = UserCFRecommender(self.cfg, n_neighbors=n_neighbors)
        self._popular = PopularRecommender(self.cfg)
        self._content = ContentRecommender(self.cfg)
        self._components: dict[str, BaseRecommender] = {
            "itemcf": self._itemcf,
            "usercf": self._usercf,
            "popular": self._popular,
            "content": self._content,
        }
        self.ref_date = None

    def fit(self, behaviors: pd.DataFrame, items: pd.DataFrame,
            orders: pd.DataFrame | None = None, order_items: pd.DataFrame | None = None,
            ref_date: pd.Timestamp | None = None) -> "HybridRecommender":
        """分别训练 4 路子模型。"""
        self.load_context(items, orders, order_items)
        for c in self._components.values():
            c.fit(behaviors, items, orders, order_items, ref_date=ref_date)
        self.ref_date = getattr(self._popular, "ref_date", None)
        return self

    def score_candidates(self, user_id: str, candidates: pd.Index) -> pd.DataFrame:
        """各分量归一化分数（未过滤，供融合/分析）。"""
        frames: dict[str, pd.Series] = {}
        for k in _HYBRID_ORDER:
            comp = self._components[k]
            s = comp.score_candidates(user_id, candidates).reindex(candidates).fillna(0.0)
            frames[k] = minmax_01(s) * float(self.hybrid_weights.get(k, 0.0))
        return pd.DataFrame(frames)

    def _rank(self, user_id: str, candidates: pd.Index, top_k: int) -> pd.DataFrame:
        comp_df = self.score_candidates(user_id, candidates)
        total = comp_df.sum(axis=1).sort_values(ascending=False)
        ranked = total.head(top_k).copy().reset_index()
        ranked.columns = ["item_id", "score"]
        _weight_labels = {"itemcf": "物品协同", "usercf": "用户协同", "popular": "热门推荐", "content": "内容推荐"}
        _weights_str = "、".join(f"{_weight_labels.get(k, k)} {v}" for k, v in self.hybrid_weights.items())
        ranked["reason"] = (
            "混合召回：物品协同 + 用户协同 + 热门 + 内容 四路分数归一化后加权融合"
            f"（权重：{_weights_str}）"
        )
        ranked["score"] = ranked["score"].round(4)
        return ranked[["item_id", "score", "reason"]]