"""Popular 推荐（Phase 11，开发文档第 49.9 节 / 35.1 节）。

热度分（必须标准化 + 时间衰减 + 权重可配置）：
    每个行为类型分量为 max-normalization 到 [0,1] 的行为加权分（含时间衰减），
    score = w_pv*pv_score + w_click*click_score + w_collect*collect_score
          + w_cart*cart_score + w_buy*buy_score
最终热度分再做一次 min-max 标准化到 [0,1]，便于跨策略比较。

冷启动：新用户 / 少行为用户直接返回全局热门 Top-K（开发文档第 35.6 节）。
"""

from __future__ import annotations

import pandas as pd

from analysis.analysis.base import BEHAVIOR_TYPES

from .base import BaseRecommender, minmax_01, weighted_behavior_score
from .config import RecommendConfig


def _normalize_component(s: pd.Series) -> pd.Series:
    """行为分量标准化：除以该分量的最大值（max-normalization），映射到 [0,1]。

    与全局 min-max 不同：单一商品拥有某行为时其分量为 1（即为该分量最热），
    否则权重对比会丢失（如 1 次 buy 永远比不过大量 pv）。
    全 0 或空时返回 0。
    """
    if len(s) == 0:
        return pd.Series(dtype=float)
    mx = float(s.max())
    if mx <= 0:
        return pd.Series(0.0, index=s.index)
    return s / mx


class PopularRecommender(BaseRecommender):
    """基于行为权重 + 时间衰减的全局热门推荐器。"""

    name = "popular"

    def fit(self, behaviors: pd.DataFrame, items: pd.DataFrame,
            orders: pd.DataFrame | None = None, order_items: pd.DataFrame | None = None,
            ref_date: pd.Timestamp | None = None) -> "PopularRecommender":
        """基于全量行为计算商品热度。

        参数:
            behaviors: user_behaviors.csv，含 item_id / behavior_type / event_date
            items: items.csv（含 item_id / status / 名称等维度）
            orders / order_items: 用于"已购买"过滤
            ref_date: 热度参考日（None=取行为最大日期）
        """
        self.load_context(items, orders, order_items)
        if ref_date is None:
            ref_date = pd.to_datetime(behaviors["event_date"], errors="coerce").dt.normalize().max()
        ref_date = pd.Timestamp(ref_date).normalize()

        # 每个行为类型独立加时间衰减加权聚合，再分别标准化
        components: dict[str, pd.Series] = {}
        for bt in BEHAVIOR_TYPES:
            sub = behaviors[behaviors["behavior_type"] == bt]
            if len(sub) == 0:
                components[bt] = pd.Series(dtype=float)
                continue
            raw = weighted_behavior_score(sub, self.cfg, ref_date)
            components[bt] = _normalize_component(raw)

        # 合并为表，缺失行为类型补 0
        score_table = pd.concat(components.values(), axis=1, keys=list(components.keys())).fillna(0.0)
        score_table["score"] = sum(
            w * score_table[bt] for bt, w in self.cfg.behavior_weights.items() if bt in score_table
        )
        score_table["score"] = minmax_01(score_table["score"])
        score_table = score_table.sort_values("score", ascending=False)

        self.score_table = score_table
        self.ref_date = ref_date
        return self

    def score_candidates(self, user_id: str, candidates: pd.Index) -> pd.Series:
        """候选商品 Popular 分数（未过滤，供 Hybrid 融合）。"""
        table = self.score_table
        return table["score"].reindex(candidates).fillna(0.0)

    def _rank(self, user_id: str, candidates: pd.Index, top_k: int) -> pd.DataFrame:
        """取候选商品中热度分最高的 top_k 个。"""
        table = self.score_table
        cand = candidates.intersection(table.index)
        ranked = table.loc[cand].sort_values("score", ascending=False).head(top_k).copy()
        ranked["item_id"] = ranked.index
        ranked["reason"] = "全网热门：按 PV/Click/Collect/Cart/Buy 加权并叠加时间衰减计算人气"
        return ranked.reset_index(drop=True)[["item_id", "score", "reason"]]