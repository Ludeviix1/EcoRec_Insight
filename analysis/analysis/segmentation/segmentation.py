"""用户分群（开发文档第 23.2 节）。

除 RFM 外，进阶实现 KMeans 无监督分群。

特征（标准化后聚类）：
total_pv / total_click / total_buy / total_amount /
avg_order_amount / purchase_frequency / recency

输出 cluster_id / cluster_name，并对聚类结果做业务解释：
- 群名根据簇内特征均值自动命名（高价值活跃/中价值潜力/活跃潜在/低频沉睡/流失风险）；
- 解释基于聚类中心的特征画像。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from ..base import safe_div

# 聚类特征（开发文档第 23.2 节）
CLUSTER_FEATURES: tuple[str, ...] = (
    "total_pv", "total_click", "total_buy", "total_amount",
    "avg_order_amount", "purchase_frequency", "recency",
)

# 全局随机种子（可复现）
RANDOM_STATE = 42


@dataclass(frozen=True)
class SegmentConfig:
    """用户分群配置。"""

    n_clusters: int = 4             # 聚类数


def user_segmentation(
    behaviors: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: SegmentConfig | None = None,
) -> dict:
    """KMeans 用户分群。

    参数:
        behaviors: user_behaviors.csv，至少含 user_id / behavior_type / event_date
        orders: orders.csv，至少含 user_id / total_amount / status / order_time
        cfg: 分群配置

    返回:
        dict:
        - definition / features / n_clusters / random_state
        - clusters: list[{"cluster_id","cluster_name","size","ratio",
                          "feature_means": {...}, "interpretation"}]
        - users: list[{"user_id","cluster_id","cluster_name"}]
    """
    cfg = cfg or SegmentConfig()

    feats = _build_features(behaviors, orders)
    if feats.empty:
        return {
            "definition": "无可用行为数据，未进行分群。",
            "features": list(CLUSTER_FEATURES),
            "n_clusters": cfg.n_clusters,
            "random_state": RANDOM_STATE,
            "clusters": [],
            "users": [],
        }

    n_clusters = min(cfg.n_clusters, len(feats))
    X = feats[list(CLUSTER_FEATURES)].to_numpy(dtype=float)
    X_scaled = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=RANDOM_STATE).fit(X_scaled)
    feats["_label"] = km.labels_

    # 按群规模降序，重编号 cluster_id（规模最大 -> 0）
    sizes = feats.groupby("_label").size().sort_values(ascending=False)
    rank = {old: new for new, old in enumerate(sizes.index)}
    feats["cluster_id"] = feats["_label"].map(rank)

    clusters = []
    for cid in range(n_clusters):
        sub = feats[feats["cluster_id"] == cid]
        means = {f: round(float(sub[f].mean()), 4) for f in CLUSTER_FEATURES}
        means["recency"] = round(float(sub["recency"].mean()), 1)
        name, interp = _interpret(means)
        clusters.append({
            "cluster_id": int(cid),
            "cluster_name": name,
            "size": int(len(sub)),
            "ratio": safe_div(len(sub), len(feats)),
            "feature_means": means,
            "interpretation": interp,
        })

    user_list = [
        {
            "user_id": str(r["user_id"]),
            "cluster_id": int(r["cluster_id"]),
            "cluster_name": clusters[int(r["cluster_id"])]["cluster_name"],
        }
        for r in feats.sort_values("user_id").to_dict("records")
    ]

    return {
        "definition": (
            "KMeans 无监督分群：特征 total_pv/total_click/total_buy/total_amount/"
            "avg_order_amount/purchase_frequency/recency，标准化后聚类；"
            "群名根据簇特征均值自动命名；cluster_id 按群规模降序重编号。"
        ),
        "features": list(CLUSTER_FEATURES),
        "n_clusters": int(n_clusters),
        "random_state": RANDOM_STATE,
        "clusters": clusters,
        "users": user_list,
    }


def _build_features(behaviors: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """构建每用户聚类特征（user_id 索引 DataFrame）。"""
    beh = behaviors.copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh = beh.dropna(subset=["event_date"])
    if beh.empty:
        return pd.DataFrame(columns=["user_id"] + list(CLUSTER_FEATURES))
    as_of = beh["event_date"].max()

    pivot = beh.groupby(["user_id", "behavior_type"]).size().unstack(fill_value=0)
    for bt in ("pv", "click", "collect", "cart", "buy"):
        if bt not in pivot.columns:
            pivot[bt] = 0
    pivot = pivot[["pv", "click", "collect", "cart", "buy"]]

    last_active = beh.groupby("user_id")["event_date"].max()
    recency = (as_of - last_active).dt.days.rename("recency")

    paid = orders[orders["status"] == "paid"].copy()
    paid["order_time"] = pd.to_datetime(paid["order_time"], errors="coerce")
    amt = paid.groupby("user_id")["total_amount"].sum().rename("total_amount")
    cnt = paid.groupby("user_id").size().rename("purchase_count")

    df = pivot.join(recency).join(amt).join(cnt)
    df["total_amount"] = df["total_amount"].fillna(0.0)
    df["purchase_count"] = df["purchase_count"].fillna(0)
    df["recency"] = df["recency"].fillna(9999).astype(int)
    df["avg_order_amount"] = [safe_div(a, c) for a, c in zip(df["total_amount"], df["purchase_count"])]
    df = df.rename(columns={
        "pv": "total_pv", "click": "total_click", "buy": "total_buy",
        "purchase_count": "purchase_frequency",
    })
    for col in ("total_pv", "total_click", "total_buy", "purchase_frequency"):
        df[col] = df[col].astype(int)
    df = df[list(CLUSTER_FEATURES)]
    return df.reset_index()


def _interpret(means: dict) -> tuple[str, str]:
    """根据簇特征均值给群命名并生成业务解释。"""
    amount = means["total_amount"]
    recency = means["recency"]
    freq = means["purchase_frequency"]
    pv = means["total_pv"]

    if amount >= 5000 and freq >= 3:
        name, interp = "高价值活跃", "消费高、复购频，是核心利润贡献用户，应重点维护。"
    elif amount >= 2000 and pv >= 50:
        name, interp = "中价值潜力", "有较高消费但与高价值群有差距，可通过交叉营销提升客单价。"
    elif recency <= 30 and pv >= 30:
        name, interp = "活跃潜在", "行为活跃但购买转化不足，需优化商品与价格匹配。"
    elif recency <= 60:
        name, interp = "低频沉睡", "近期仍有行为但消费/活跃偏低，需唤醒刺激。"
    else:
        name, interp = "流失风险", "长期无活跃，需召回或识别流失原因。"
    return name, interp