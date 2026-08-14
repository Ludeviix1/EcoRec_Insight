"""商品级特征（Phase 8，开发文档第 49.6 节）。

流程：过去 observation_days 天行为/销售聚合 + 商品静态画像
      => "每个商品一行"的商品特征表，供 Phase 12 Content-Base 与商品画像复用。

防泄漏要点：
- 行为 / 销售聚合**只使用观察窗口内**的记录；
- 不读取任何未来标签；
- 静态画像（上架时间、价格、库存、状态）为 as-of 属性。
"""

from __future__ import annotations

import pandas as pd

from analysis.analysis.base import safe_div

from .base import count_matrix, observation_window
from .config import BEHAVIOR_TYPES, FeatureConfig


def build_item_features(
    items: pd.DataFrame,
    behaviors: pd.DataFrame,
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: FeatureConfig | None = None,
) -> pd.DataFrame:
    """构建商品级特征表。

    参数:
        items: items.csv，含 item_id / item_name / category_id / brand / price / stock / status / created_at
        behaviors: user_behaviors.csv，含 item_id / user_id / behavior_type / event_date
        order_items: order_items.csv，含 order_id / item_id / quantity / amount
        orders: orders.csv，含 order_id / order_time / status（过滤 paid 且限定窗口）
        cfg: 特征配置（观察窗口 / 权重）

    返回:
        DataFrame，每商品一行；字段见 feature_dictionary.json（table=item_features）。
    """
    cfg = cfg or FeatureConfig()
    obs_start, obs_end = observation_window(cfg, behaviors)

    # ---- 静态画像（as-of 属性）----
    dim = items[
        ["item_id", "item_name", "category_id", "brand", "price", "stock", "status", "created_at"]
    ].copy()
    created = pd.to_datetime(dim["created_at"], errors="coerce")
    dim["days_listed"] = (obs_end - created).dt.days.fillna(0).clip(lower=0).astype(int)
    dim["price"] = pd.to_numeric(dim["price"], errors="coerce")
    dim["stock"] = pd.to_numeric(dim["stock"], errors="coerce")
    dim["status"] = pd.to_numeric(dim["status"], errors="coerce")

    # ---- 观察窗口内行为 ----
    beh = behaviors[["item_id", "user_id", "behavior_type", "event_date"]].copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh = beh[beh["event_date"].between(obs_start, obs_end)].copy()

    counts = count_matrix(beh, "item_id")
    counts.columns = [f"n_{c}" for c in counts.columns]
    counts["total_behaviors"] = counts[[f"n_{bt}" for bt in BEHAVIOR_TYPES]].sum(axis=1)

    n_unique_users = beh.groupby("item_id")["user_id"].nunique().rename("n_unique_users")
    last_active = beh.groupby("item_id")["event_date"].max().rename("last_active")

    # ---- 观察窗口内销售（仅 paid）----
    ord_ = orders[["order_id", "user_id", "order_time", "status"]].copy()
    ord_["order_time"] = pd.to_datetime(ord_["order_time"], errors="coerce")
    ord_ = ord_[ord_["order_time"].between(obs_start, obs_end) & (ord_["status"] == "paid")].copy()
    paid_ids = set(ord_["order_id"])

    oi = order_items[order_items["order_id"].isin(paid_ids)].copy()
    oi["quantity"] = pd.to_numeric(oi["quantity"], errors="coerce").fillna(0)
    oi["amount"] = pd.to_numeric(oi["amount"], errors="coerce").fillna(0)
    sales = oi.groupby("item_id").agg(
        units_sold=("quantity", "sum"),
        gmv=("amount", "sum"),
        n_paid_orders=("order_id", "nunique"),
    )
    buying_users = (
        oi.merge(ord_[["order_id", "user_id"]], on="order_id")
        .groupby("item_id")["user_id"]
        .nunique()
        .rename("n_buying_users")
    )

    # ---- 合并 ----
    out = dim
    for part in (
        counts.reset_index(),
        n_unique_users.reset_index(),
        last_active.reset_index(),
        sales.reset_index(),
        buying_users.reset_index(),
    ):
        out = out.merge(part, on="item_id", how="left")

    int_cols = (
        [f"n_{bt}" for bt in BEHAVIOR_TYPES]
        + ["total_behaviors", "n_unique_users", "units_sold", "n_paid_orders", "n_buying_users"]
    )
    for c in int_cols:
        out[c] = out[c].fillna(0).astype(int)
    out["gmv"] = out["gmv"].fillna(0.0)
    out["last_behavior_offset_days"] = (
        (obs_end - out["last_active"]).dt.days.fillna(cfg.observation_days).astype(int)
    )
    out = out.drop(columns=["last_active"])

    out["conversion_rate"] = [
        safe_div(b, p) for b, p in zip(out["n_buy"], out["n_pv"])
    ]
    out["heat_score"] = (
        sum(w * out[f"n_{bt}"] for bt, w in cfg.behavior_weights.items())
        + out["gmv"] / 100.0
    )

    cols = [
        "item_id", "item_name", "category_id", "brand", "price", "stock", "status", "days_listed",
        "n_pv", "n_click", "n_collect", "n_cart", "n_buy", "total_behaviors",
        "n_unique_users", "last_behavior_offset_days",
        "units_sold", "gmv", "n_paid_orders", "n_buying_users",
        "conversion_rate", "heat_score",
    ]
    return out[cols].sort_values("item_id").reset_index(drop=True)