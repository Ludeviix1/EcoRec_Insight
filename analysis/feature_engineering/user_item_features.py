"""用户-商品交互特征（Phase 8，开发文档第 49.6 节）。

流程：过去 observation_days 天行为
      => "每个有行为的 (user_id, item_id) 对一行"的交互特征表，
         供 Phase 11~14 召回 / 交叉特征直接复用。

防泄漏要点：
- 只使用观察窗口内的行为记录；
- 不读取任何未来标签；
- 表内只有窗口内发生过行为的用户-商品对。
"""

from __future__ import annotations

import pandas as pd

from .base import count_matrix, observation_window
from .config import BEHAVIOR_TYPES, FeatureConfig


def build_user_item_features(
    behaviors: pd.DataFrame,
    items: pd.DataFrame,
    cfg: FeatureConfig | None = None,
) -> pd.DataFrame:
    """构建用户-商品交互特征表。

    参数:
        behaviors: user_behaviors.csv，含 user_id / item_id / behavior_type / event_time / event_date
        items: items.csv，含 item_id / category_id
        cfg: 特征配置（观察窗口 / 权重）

    返回:
        DataFrame，每个窗口内发生过行为的 (user_id, item_id) 对一行；
        字段见 feature_dictionary.json（table=user_item_features）。
    """
    cfg = cfg or FeatureConfig()
    obs_start, obs_end = observation_window(cfg, behaviors)

    df = behaviors[["user_id", "item_id", "behavior_type", "event_time", "event_date"]].copy()
    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.normalize()
    df = df[df["event_date"].between(obs_start, obs_end)].copy()

    counts = count_matrix(df, ["user_id", "item_id"])
    counts.columns = [f"n_{c}" for c in counts.columns]
    counts["total_behaviors"] = counts[[f"n_{bt}" for bt in BEHAVIOR_TYPES]].sum(axis=1)

    g = df.groupby(["user_id", "item_id"])["event_date"]
    first_date = g.min().rename("first_date")
    last_date = g.max().rename("last_date")

    out = counts.reset_index()
    out = out.merge(first_date.reset_index(), on=["user_id", "item_id"], how="left")
    out = out.merge(last_date.reset_index(), on=["user_id", "item_id"], how="left")

    out["first_activity_offset_days"] = (out["first_date"] - obs_start).dt.days.astype(int)
    out["last_activity_offset_days"] = (out["last_date"] - obs_start).dt.days.astype(int)
    out["days_since_last"] = (obs_end - out["last_date"]).dt.days.astype(int)
    out = out.drop(columns=["first_date", "last_date"])

    out["is_bought"] = (out["n_buy"] > 0).astype(int)
    out["weighted_score"] = sum(w * out[f"n_{bt}"] for bt, w in cfg.behavior_weights.items())

    cat_map = items[["item_id", "category_id"]].drop_duplicates("item_id")
    out = out.merge(cat_map, on="item_id", how="left")

    cols = [
        "user_id", "item_id", "category_id",
        "n_pv", "n_click", "n_collect", "n_cart", "n_buy", "total_behaviors",
        "weighted_score", "first_activity_offset_days", "last_activity_offset_days",
        "days_since_last", "is_bought",
    ]
    return out[cols].sort_values(["user_id", "item_id"]).reset_index(drop=True)