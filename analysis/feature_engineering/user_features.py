"""用户级特征（Phase 8，开发文档第 49.6 节）。

流程：过去 observation_days 天行为/订单聚合 + 用户静态画像
      => "每个用户一行"的用户特征表，供 Phase 9 购买预测直接消费。

防泄漏要点：
- 行为 / 订单 / 明细聚合**只使用观察窗口内**的记录；
- 不读取任何未来标签（Phase 9 才构造 label）；
- 静态画像（注册时间、性别、年龄）为 as-of 属性，不随标签时间变化。
"""

from __future__ import annotations

import pandas as pd

from analysis.analysis.base import safe_div

from .base import count_matrix, observation_window
from .config import BEHAVIOR_TYPES, FeatureConfig


def build_user_features(
    users: pd.DataFrame,
    behaviors: pd.DataFrame,
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    items: pd.DataFrame,
    cfg: FeatureConfig | None = None,
) -> pd.DataFrame:
    """构建用户级特征表。

    参数:
        users: users.csv，含 user_id / age / gender / register_time
        behaviors: user_behaviors.csv，含 user_id / item_id / behavior_type / event_time / event_date / channel / device_type
        orders: orders.csv，含 order_id / user_id / order_time / total_amount / status
        order_items: order_items.csv，含 order_id / item_id / quantity / amount
        items: items.csv，含 item_id / category_id
        cfg: 特征配置（观察窗口 / 会话阈值 / 权重）

    返回:
        DataFrame，每用户一行；字段见 feature_dictionary.json（table=user_features）。
    """
    cfg = cfg or FeatureConfig()
    n_obs_days = max(cfg.observation_days, 1)
    obs_start, obs_end = observation_window(cfg, behaviors)

    # ---- 静态画像（as-of 属性）----
    prof = users[["user_id", "age", "gender", "register_time"]].copy()
    prof["register_time"] = pd.to_datetime(prof["register_time"], errors="coerce")
    reg_days = (obs_end - prof["register_time"]).dt.days
    prof["register_days"] = reg_days.fillna(0).clip(lower=0).astype(int)
    prof["is_new_in_window"] = (
        (prof["register_time"] >= obs_start) & (prof["register_time"] <= obs_end)
    ).astype(int)
    prof["age"] = pd.to_numeric(prof["age"], errors="coerce")
    gender = prof["gender"].fillna("")
    prof["gender_m"] = (gender == "M").astype(int)
    prof["gender_f"] = (gender == "F").astype(int)

    # ---- 观察窗口内行为（只能看到窗口内的数据）----
    beh = behaviors[
        ["user_id", "item_id", "behavior_type", "event_time", "event_date", "channel", "device_type"]
    ].copy()
    beh["event_time"] = pd.to_datetime(beh["event_time"], errors="coerce")
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh = beh[beh["event_date"].between(obs_start, obs_end)].copy()

    counts = count_matrix(beh, "user_id")
    counts.columns = [f"n_{c}" for c in counts.columns]

    cat_map = items[["item_id", "category_id"]].drop_duplicates("item_id")
    beh_cat = beh.merge(cat_map, on="item_id", how="left")
    n_distinct_categories = (
        beh_cat.groupby("user_id")["category_id"].nunique().rename("n_distinct_categories")
    )

    b_agg = beh.groupby("user_id").agg(
        total_behaviors=("event_time", "size"),
        n_active_days=("event_date", "nunique"),
        n_distinct_items=("item_id", "nunique"),
        n_channels=("channel", "nunique"),
        n_devices=("device_type", "nunique"),
    )

    # 会话数：同一用户相邻行为间隔超过 session_gap_minutes 视为新会话
    gap = pd.Timedelta(minutes=cfg.session_gap_minutes)
    b2 = beh.sort_values(["user_id", "event_time"])
    new_session = (b2["user_id"] != b2["user_id"].shift(1)) | (
        b2["event_time"] - b2["event_time"].shift(1) > gap
    )
    b2["_sid"] = new_session.cumsum()
    n_sessions = b2.groupby("user_id")["_sid"].nunique().rename("n_sessions")

    last_active = beh.groupby("user_id")["event_date"].max().rename("last_active")
    first_active = beh.groupby("user_id")["event_date"].min().rename("first_active")
    top_channel = (
        beh.groupby("user_id")["channel"]
        .agg(lambda s: s.value_counts().idxmax() if len(s) else "")
        .rename("top_channel")
    )
    top_device = (
        beh.groupby("user_id")["device_type"]
        .agg(lambda s: s.value_counts().idxmax() if len(s) else "")
        .rename("top_device")
    )

    # ---- 观察窗口内支付订单 / 明细（只能看到窗口内的数据）----
    ord_ = orders[["order_id", "user_id", "order_time", "total_amount", "status"]].copy()
    ord_["order_time"] = pd.to_datetime(ord_["order_time"], errors="coerce")
    ord_ = ord_[ord_["order_time"].between(obs_start, obs_end) & (ord_["status"] == "paid")].copy()
    paid_ids = set(ord_["order_id"])

    o_agg = ord_.groupby("user_id").agg(
        paid_order_count=("order_id", "size"),
        paid_gmv=("total_amount", "sum"),
        max_order_amount=("total_amount", "max"),
        purchase_days=("order_time", lambda s: s.dt.normalize().nunique()),
    )
    oi = order_items[order_items["order_id"].isin(paid_ids)].merge(
        ord_[["order_id", "user_id"]], on="order_id"
    )
    purchased_items = oi.groupby("user_id")["item_id"].nunique().rename("purchased_items")
    purchased_categories = (
        oi.merge(cat_map, on="item_id", how="left")
        .groupby("user_id")["category_id"]
        .nunique()
        .rename("purchased_categories")
    )

    # ---- 合并 ----
    out = prof
    for part in (
        counts.reset_index(),
        b_agg.reset_index(),
        n_distinct_categories.reset_index(),
        n_sessions.reset_index(),
        last_active.reset_index(),
        first_active.reset_index(),
        top_channel.reset_index(),
        top_device.reset_index(),
        o_agg.reset_index(),
        purchased_items.reset_index(),
        purchased_categories.reset_index(),
    ):
        out = out.merge(part, on="user_id", how="left")

    # ---- 填充与派生 ----
    int_cols = (
        [f"n_{bt}" for bt in BEHAVIOR_TYPES]
        + ["total_behaviors", "n_active_days", "n_distinct_items", "n_channels",
           "n_devices", "n_distinct_categories", "n_sessions",
           "paid_order_count", "purchase_days", "purchased_items", "purchased_categories"]
    )
    for c in int_cols:
        out[c] = out[c].fillna(0).astype(int)

    out["paid_gmv"] = out["paid_gmv"].fillna(0.0)
    out["max_order_amount"] = out["max_order_amount"].fillna(0.0)
    out["recency_days"] = (obs_end - out["last_active"]).dt.days.fillna(cfg.observation_days).astype(int)
    out["first_activity_offset_days"] = (
        (out["first_active"] - obs_start).dt.days.fillna(0).astype(int)
    )
    out["top_channel"] = out["top_channel"].fillna("")
    out["top_device"] = out["top_device"].fillna("")
    out = out.drop(columns=["last_active", "first_active", "gender"])

    out["behavior_buy_ratio"] = [
        safe_div(b, t) for b, t in zip(out["n_buy"], out["total_behaviors"])
    ]
    out["active_day_ratio"] = (out["n_active_days"] / n_obs_days).clip(upper=1.0)
    out["behaviors_per_active_day"] = [
        safe_div(t, a) for t, a in zip(out["total_behaviors"], out["n_active_days"])
    ]
    out["avg_behaviors_per_day"] = out["total_behaviors"] / n_obs_days
    out["behaviors_per_session"] = [
        safe_div(t, s) for t, s in zip(out["total_behaviors"], out["n_sessions"])
    ]
    out["click_rate"] = [safe_div(c, p) for c, p in zip(out["n_click"], out["n_pv"])]
    out["collect_rate"] = [safe_div(c, p) for c, p in zip(out["n_collect"], out["n_pv"])]
    out["cart_rate"] = [safe_div(c, p) for c, p in zip(out["n_cart"], out["n_pv"])]
    out["buy_rate"] = [safe_div(b, p) for b, p in zip(out["n_buy"], out["n_pv"])]
    out["avg_order_amount"] = [
        safe_div(g, c) for g, c in zip(out["paid_gmv"], out["paid_order_count"])
    ]
    out["has_purchase"] = (out["paid_order_count"] > 0).astype(int)

    cols = [
        "user_id", "age", "gender_m", "gender_f", "register_days", "is_new_in_window",
        "total_behaviors", "n_pv", "n_click", "n_collect", "n_cart", "n_buy",
        "behavior_buy_ratio", "n_active_days", "active_day_ratio", "behaviors_per_active_day",
        "avg_behaviors_per_day", "n_sessions", "behaviors_per_session", "recency_days",
        "first_activity_offset_days", "n_distinct_items", "n_distinct_categories",
        "n_channels", "n_devices", "top_channel", "top_device",
        "click_rate", "collect_rate", "cart_rate", "buy_rate",
        "paid_order_count", "paid_gmv", "avg_order_amount", "max_order_amount",
        "purchased_items", "purchased_categories", "purchase_days", "has_purchase",
    ]
    return out[cols].sort_values("user_id").reset_index(drop=True)