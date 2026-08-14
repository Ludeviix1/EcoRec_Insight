"""用户画像 user_profile（开发文档第 23.1 节）。

每个用户输出一份画像，包括：
- 基础属性：age / gender / city / 注册时长；
- 行为统计：pv / click / collect / cart / buy 与活跃天数；
- 购买统计：订单数 / GMV / 客单价；
- 消费能力：消费档位（低/中/高/超高）；
- 活跃时间：主要活跃小时段 / 星期偏好；
- 偏好类别 / 偏好品牌：按行为次数 Top N；
- 生命周期：复用 lifecycle 的阶段；
- RFM：复用 rfm_analysis 的 R/F/M 分；
- 渠道 / 设备：行为占比最高者。

说明：画像字段全部可 JSON 序列化；用户分群 cluster 由独立模块输出。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..base import BEHAVIOR_TYPES, safe_div
from ..lifecycle import LifecycleConfig, lifecycle_analysis
from ..rfm import RfmConfig, rfm_analysis


@dataclass(frozen=True)
class ProfileConfig:
    """用户画像配置。"""

    top_n: int = 3              # 偏好类别 / 品牌 Top N
    rfm_cfg: RfmConfig = RfmConfig()
    lifecycle_cfg: LifecycleConfig = LifecycleConfig()


def user_profile(
    users: pd.DataFrame,
    behaviors: pd.DataFrame,
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    items: pd.DataFrame,
    cfg: ProfileConfig | None = None,
) -> dict:
    """为每个用户生成画像。

    参数:
        users: users.csv，含 user_id / age / gender / city / register_time
        behaviors: user_behaviors.csv，含 user_id / item_id / behavior_type / event_date / device_type / channel / event_hour
        orders: orders.csv，含 user_id / total_amount / status / order_time
        order_items: order_items.csv，含 order_id / item_id / amount
        items: items.csv，含 item_id / category_id / brand
        cfg: 画像配置

    返回:
        dict:
        - definition
        - total_users
        - profiles: list[{user_id, 基础属性, 行为统计, 购买统计,
                           消费能力, 活跃时间, 偏好类别, 偏好品牌,
                           lifecycle_stage, rfm: {...}, 渠道, 设备}]
    """
    cfg = cfg or ProfileConfig()

    # ---- 生命周期（全量用户）----
    life = lifecycle_analysis(users, behaviors, orders, cfg.lifecycle_cfg)
    stage_map = {u["user_id"]: u["stage"] for u in life["users"]}

    # ---- RFM（购买用户）----
    rfm = rfm_analysis(orders, cfg.rfm_cfg)
    rfm_map = {u["user_id"]: u for u in rfm["users"]}

    # ---- 行为侧聚合 ----
    beh = behaviors.copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh["event_hour"] = pd.to_numeric(beh["event_hour"], errors="coerce").fillna(-1).astype(int)
    beh["event_weekday"] = beh["event_date"].dt.weekday  # 周一=0
    as_of = beh["event_date"].max()

    item_info = items[["item_id", "category_id", "brand"]].copy()
    beh_items = beh.merge(item_info, on="item_id", how="left")

    # 用户行为统计
    bcounts = beh.groupby(["user_id", "behavior_type"]).size().unstack(fill_value=0)
    for bt in BEHAVIOR_TYPES:
        if bt not in bcounts.columns:
            bcounts[bt] = 0
    bcounts = bcounts[list(BEHAVIOR_TYPES)]
    active_days = beh.groupby("user_id")["event_date"].nunique().rename("active_days")

    # 渠道 / 设备偏好
    ch_top = beh.groupby(["user_id", "channel"]).size()
    dev_top = beh.groupby(["user_id", "device_type"]).size()

    # 活跃小时与星期
    hour_mode = beh.groupby("user_id")["event_hour"].agg(lambda s: int(s.mode().iloc[0]) if len(s) else None)
    weekday_mode = beh.groupby("user_id")["event_weekday"].agg(lambda s: int(s.mode().iloc[0]) if len(s) else None)

    # 偏好类别 / 品牌
    cat_top = beh_items.groupby(["user_id", "category_id"]).size()
    brand_top = beh_items.groupby(["user_id", "brand"]).size()

    # ---- 购买侧聚合 ----
    paid = orders[orders["status"] == "paid"].copy()
    paid["order_time"] = pd.to_datetime(paid["order_time"], errors="coerce")
    paid_cnt = paid.groupby("user_id").size().rename("order_count")
    paid_gmv = paid.groupby("user_id")["total_amount"].sum().rename("gmv")
    # 客单价：用订单级平均（gmv/order_count）
    pay_table = paid_cnt.to_frame().join(paid_gmv)

    base = users.copy()
    base["register_time"] = pd.to_datetime(base["register_time"], errors="coerce")
    base = base.join(bcounts, on="user_id").join(active_days, on="user_id")
    base = base.join(pay_table, on="user_id")

    profiles = []
    for r in base.to_dict("records"):
        uid = str(r["user_id"])
        gmv = float(r["gmv"]) if pd.notna(r["gmv"]) else 0.0
        order_count = int(r["order_count"]) if pd.notna(r["order_count"]) else 0
        pv = int(r["pv"]) if pd.notna(r["pv"]) else 0
        click = int(r["click"]) if pd.notna(r["click"]) else 0
        buy = int(r["buy"]) if pd.notna(r["buy"]) else 0

        profile = {
            "user_id": uid,
            "basic": {
                "age": int(r["age"]) if pd.notna(r["age"]) else None,
                "gender": r["gender"] if pd.notna(r["gender"]) else None,
                "city": r["city"] if pd.notna(r["city"]) else None,
                "register_days": int((as_of - r["register_time"]).days)
                if pd.notna(r["register_time"]) else None,
            },
            "behavior": {
                "pv": pv, "click": click,
                "collect": int(r["collect"]) if pd.notna(r["collect"]) else 0,
                "cart": int(r["cart"]) if pd.notna(r["cart"]) else 0,
                "buy": buy,
                "active_days": int(r["active_days"]) if pd.notna(r["active_days"]) else 0,
            },
            "purchase": {
                "order_count": order_count,
                "gmv": round(gmv, 2),
                "aov": safe_div(gmv, order_count),
            },
            "spending_power": _spend_tier(gmv),
            "active_time": {
                "peak_hour": _pick(hour_mode, uid),
                "peak_weekday": _pick(weekday_mode, uid),
            },
            "preferred_categories": _top_items(cat_top, uid, cfg.top_n, key="category_id"),
            "preferred_brands": _top_items(brand_top, uid, cfg.top_n, key="brand"),
            "lifecycle_stage": stage_map.get(uid),
            "rfm": _rfm_of(rfm_map, uid),
            "channel": _argmax(ch_top, uid),
            "device": _argmax(dev_top, uid),
        }
        profiles.append(profile)

    return {
        "definition": (
            "每用户画像：基础属性/行为统计/购买统计/消费能力/活跃时间/"
            "偏好类别/偏好品牌/生命周期/RFM/渠道/设备。"
            "生命周期复用 lifecycle，RFM 复用 rfm 模块，口径一致。"
        ),
        "total_users": int(len(base)),
        "profiles": profiles,
    }


def _spend_tier(gmv: float) -> str:
    if gmv >= 10000:
        return "超高消费"
    if gmv >= 3000:
        return "高消费"
    if gmv >= 1000:
        return "中消费"
    if gmv > 0:
        return "低消费"
    return "未消费"


def _pick(series: pd.Series, uid: str):
    return int(series.get(uid)) if uid in series.index and pd.notna(series.get(uid)) else None


def _top_items(series: pd.Series, uid: str, top_n: int, key: str) -> list:
    if uid not in series.index:
        return []
    sub = series.loc[uid]
    if isinstance(sub, pd.Series):
        top = sub.nlargest(top_n)
    else:
        top = pd.Series({sub.index[0]: int(sub)}) if len(sub) else pd.Series(dtype=int)
    return [{"value": str(k), "count": int(v)} for k, v in top.items()][:top_n]


def _rfm_of(rfm_map: dict, uid: str):
    r = rfm_map.get(uid)
    if not r:
        return None
    return {
        "r_score": r["r_score"], "f_score": r["f_score"], "m_score": r["m_score"],
        "rfm_score": r["rfm_score"], "segment": r["segment"],
    }


def _argmax(series: pd.Series, uid: str):
    if uid not in series.index:
        return None
    sub = series.loc[uid]
    if isinstance(sub, pd.Series):
        return str(sub.idxmax())
    return str(sub.index[0])