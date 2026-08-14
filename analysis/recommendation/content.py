"""Content-Based 推荐（Phase 13，开发文档第 49.11 节 / 35.4 节）。

商品内容向量由以下特征构造（转换为一维稀疏向量）：
    - category   ：叶子分类 one-hot；
    - brand      ：品牌 one-hot；
    - price_range：价格分箱（qcut 离散化）one-hot；
    - item tags  ：商品名分词后 TF-IDF（去掉品牌 token，避免与 brand 冗余）。

相似度：商品向量余弦相似度（cosine similarity）。

推荐流程（与开发文档第 35.2 节 Item-CF 流程对齐）：
    用户历史商品（种子） → 相似商品（内容余弦） → 分数累加（种子权重 × 相似度）
    → 过滤（已购买 / 已下架 / 不存在 / 重复）→ Top-K

必须解决（开发文档第 49.11 节）：
    - 已购买商品过滤；- 已下架商品过滤；- Top-K；- 冷启动商品/新用户。
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder

from .base import BaseRecommender, minmax_01, time_decay_weight
from .config import RecommendConfig

_TAG_TOKEN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def build_content_matrix(
    items: pd.DataFrame,
    n_price_bins: int = 4,
    *,
    dummy: bool = False,
) -> tuple[sparse.csr_matrix, pd.Index, dict]:
    """构造商品内容稀疏向量矩阵。

    参数:
        items: items.csv（含 item_id / category_id / brand / price / item_name）
        n_price_bins: 价格分箱数（price_range）
        dummy: True 时用小样本数据做功能性测试（见 test_phase13）

    返回:
        (向量矩阵 csr [n_items×n_feat], item_id 索引, 特征信息 dict)
    """
    df = items.copy()
    df["item_id"] = df["item_id"].astype(str)
    df = df.set_index("item_id")

    cats = df["category_id"].astype(str)
    brands = df["brand"].astype(str)
    prices = df["price"].astype(float)

    # price_range：qcut 分箱，箱数不足时报错则退化为 cut
    try:
        bins = pd.qcut(prices, q=n_price_bins, labels=False, duplicates="drop")
    except ValueError:
        bins = pd.cut(prices, bins=n_price_bins, labels=False, duplicates="drop")
    bins = bins.astype(str).fillna("-1")
    price_bin = pd.Series(["price_" + b for b in bins], index=df.index)

    # item tags：商品名分词（去掉品牌 token）
    tags: list[str] = []
    for it in df.index:
        name = str(df.loc[it, "item_name"]) if "item_name" in df.columns else ""
        toks = _TAG_TOKEN.findall(name)
        if "brand" in df.columns:
            toks = [t for t in toks if t != str(df.loc[it, "brand"])]
        tags.append(" ".join(toks))

    info = {
        "n_items": len(df),
        "n_price_bins": int(bins.nunique()),
        "price_bin": {i: b for i, b in zip(df.index, price_bin)},
        "tag_example": tags[:2],
    }

    # 编码为稀疏向量并拼接
    enc_cat = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    enc_brand = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    enc_price = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    tfidf = TfidfVectorizer(token_pattern=r"[\u4e00-\u9fffA-Za-z0-9]+", min_df=1)

    X_cat = enc_cat.fit_transform(cats.to_frame())
    X_brand = enc_brand.fit_transform(brands.to_frame())
    X_price = enc_price.fit_transform(price_bin.to_frame(name="bin"))
    X_tag = tfidf.fit_transform(tags)

    X = sparse.hstack([X_cat, X_brand, X_price, X_tag]).tocsr().astype(np.float32)
    return X, df.index, info


class ContentRecommender(BaseRecommender):
    """基于商品内容特征（分类/品牌/价格档/标签）余弦相似度的推荐器。

    冷启动（开发文档第 35.6 节）：
    - 新用户：无种子商品 → 回退全局热门（Popular Top-K）；
    - 少行为用户：少量种子，同样走内容相似；
    - 新商品：从未被交互也能被内容相似召回（内容特征不需行为）。
    """

    name = "content"

    def __init__(self, cfg: RecommendConfig | None = None):
        super().__init__(cfg)
        self._X: sparse.csr_matrix | None = None        # 内容向量矩阵
        self._item_index: pd.Index | None = None        # item_id 顺序（与 _X 行对应）
        self._user_seed: dict[str, pd.Series] = {}      # user_id -> {item_id: 种子权重}
        self._fallback: pd.Series | None = None         # 全局热门兜底（冷启动）

    def fit(self, behaviors: pd.DataFrame, items: pd.DataFrame,
            orders: pd.DataFrame | None = None, order_items: pd.DataFrame | None = None,
            ref_date: pd.Timestamp | None = None) -> "ContentRecommender":
        """构建内容向量并保存用户种子（历史行为加权+时间衰减）。"""
        self.load_context(items, orders, order_items)
        X, index, info = build_content_matrix(items, self.cfg.n_price_bins)
        self._X = X
        self._item_index = index
        self._info = info

        # 用户种子：对用户历史行为加权（行为权重 × 时间衰减）聚合到商品
        beh = behaviors[["user_id", "item_id", "behavior_type", "event_date"]].copy()
        beh["item_id"] = beh["item_id"].astype(str)
        if ref_date is None:
            ref_date = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize().max()
        ref_date = pd.Timestamp(ref_date).normalize()
        beh["decay"] = time_decay_weight(beh["event_date"], ref_date, self.cfg.half_life_days).to_numpy()
        beh["weight"] = beh["behavior_type"].map(self.cfg.behavior_weights).fillna(0.0) * beh["decay"]
        for uid, g in beh.groupby("user_id"):
            s = g.groupby("item_id")["weight"].sum()
            s = s[s > 0]
            self._user_seed[str(uid)] = s

        # 兜底热门（新用户无种子时用）：全行为加权分
        raw = beh.groupby("item_id")["weight"].sum()
        self._fallback = minmax_01(raw)
        self.ref_date = ref_date
        return self

    def _cosine_scores(self, seeds: pd.Series, cand_ids: pd.Index) -> pd.Series:
        """种子商品 → 候选商品的内容余弦分数（Σ 种子权重×相似度）。"""
        if self._X is None or self._item_index is None:
            raise RuntimeError("请先调用 fit()")
        seed_ids = list(seeds.index)
        seed_rows = self._item_index.get_indexer(seed_ids)
        cand_rows = self._item_index.get_indexer(cand_ids)
        Xs = self._X[seed_rows]
        Xc = self._X[cand_rows]

        # L2 归一化后点积即余弦相似度
        s_norm = np.asarray(Xs.power(2).sum(axis=1)).ravel() ** 0.5
        c_norm = np.asarray(Xc.power(2).sum(axis=1)).ravel() ** 0.5
        with np.errstate(divide="ignore", invalid="ignore"):
            cos = (Xs @ Xc.T).toarray()
            cos = cos / np.outer(s_norm, c_norm + 1e-9)
        cos = pd.DataFrame(cos, index=seed_ids, columns=cand_ids)
        score = (cos * seeds.reindex(seed_ids).to_numpy()[:, None]).sum(axis=0)
        score = score.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        return score

    def _rank(self, user_id: str, candidates: pd.Index, top_k: int) -> pd.DataFrame:
        """对候选商品按内容相似打分并返回前 top_k 行。"""
        seeds = self._user_seed.get(str(user_id), pd.Series(dtype=float))
        if len(seeds) == 0 or len(candidates) == 0:
            # 冷启动新用户：回退全局热门
            fall = self._fallback
            if fall is None or len(fall) == 0:
                return pd.DataFrame(columns=["item_id", "score", "reason"]).iloc[0:0]
            cand_fall = fall.reindex(candidates.intersection(fall.index)).dropna()
            ranked = cand_fall.sort_values(ascending=False).head(top_k).copy()
            ranked = ranked.reset_index()
            ranked.columns = ["item_id", "score"]
            ranked["reason"] = "冷启动：全局热门兜底（新用户无历史行为）"
            out = ranked[["item_id", "score", "reason"]]
            out["score"] = out["score"].round(4)
            return out

        # 限制种子数量（取权重最高的 sim_top 个）以防矩阵过大
        seed_top = seeds.sort_values(ascending=False).head(self.cfg.sim_top)
        score = self._cosine_scores(seed_top, candidates)
        score = score.sort_values(ascending=False)
        ranked = score.head(top_k).copy().reset_index()
        ranked.columns = ["item_id", "score"]
        ranked["reason"] = "内容相似：与你最近浏览/加购的商品（分类/品牌/价格档/标签）相似"
        ranked["score"] = ranked["score"].round(4)
        return ranked[["item_id", "score", "reason"]]