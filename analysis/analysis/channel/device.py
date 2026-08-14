"""设备分析（开发文档第 28.2 节）。

设备：mobile / pc / tablet。

指标：活跃（用户数）、行为占比、转化（点击/购买率）、GMV、客单价、使用时间
（活跃小时分布 + 平均会话时长估计）。

口径（明确定义）：
- 活跃：该设备产生过行为的去重用户；
- 转化率 = click/pv、buy/pv（设备内行为汇总）；
- GMV / 客单价：该设备购买用户（设备偏好归因）的 paid 订单汇总；
- 使用时间：给出设备活跃小时分布（0~23 点）与晚间占比(18~23 点)。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..base import DEVICE_TYPES, safe_div


@dataclass(frozen=True)
class DeviceConfig:
    """设备分析配置。"""

    new_user_days: int = 30     # 与渠道一致，供参考（暂未使用）


def device_analysis(
    users: pd.DataFrame,
    behaviors: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: DeviceConfig | None = None,
) -> dict:
    """按设备汇总质量指标。

    参数:
        users: users.csv，至少含 user_id
        behaviors: user_behaviors.csv，至少含 user_id / device_type / behavior_type / event_hour
        orders: orders.csv，至少含 user_id / total_amount / status
        cfg: 设备分析配置

    返回:
        dict:
        - definition
        - devices: list[{"device","users","behavior_ratio","pv","click","cart","buy",
                         "click_rate","buy_rate","orders","gmv","aov",
                         "evening_ratio","peak_hour"}]
    """
    c = cfg or DeviceConfig()

    beh = behaviors.copy()
    beh["event_hour"] = pd.to_numeric(beh["event_hour"], errors="coerce").fillna(-1).astype(int)

    total_users = beh["user_id"].nunique()
    rows = []
    for dev in DEVICE_TYPES:
        sub = beh[beh["device_type"] == dev]
        users_dev = set(sub["user_id"])
        counts = sub["behavior_type"].value_counts().to_dict()
        pv = int(counts.get("pv", 0))
        click = int(counts.get("click", 0))
        collect = int(counts.get("collect", 0))
        cart = int(counts.get("cart", 0))
        buy = int(counts.get("buy", 0))

        buy_users = set(sub.loc[sub["behavior_type"] == "buy", "user_id"])
        ch_orders = int(((orders["status"] == "paid") & (orders["user_id"].isin(buy_users))).sum())
        dev_gmv = orders.loc[
            (orders["status"] == "paid") & (orders["user_id"].isin(buy_users)),
            "total_amount",
        ].sum()

        hours = sub["event_hour"]
        hours_valid = hours[hours >= 0]
        evening = int(((hours_valid >= 18) & (hours_valid <= 23)).sum())
        evening_ratio = safe_div(evening, len(hours_valid))
        peak_hour = int(hours_valid.mode().iloc[0]) if len(hours_valid) else None

        rows.append({
            "device": dev,
            "users": int(len(users_dev)),
            "behavior_ratio": safe_div(len(sub), len(beh)),
            "pv": pv,
            "click": click,
            "collect": collect,
            "cart": cart,
            "buy": buy,
            "click_rate": safe_div(click, pv),
            "buy_rate": safe_div(buy, pv),
            "orders": ch_orders,
            "gmv": round(float(dev_gmv), 2),
            "aov": safe_div(dev_gmv, ch_orders),
            "evening_ratio": round(float(evening_ratio), 4),
            "peak_hour": peak_hour,
        })

    rows.sort(key=lambda r: r["gmv"], reverse=True)
    return {
        "definition": (
            "设备活跃=该设备行为去重用户；点击率=click/pv；购买率=buy/pv；"
            "GMV/客单价=设备购买用户的 paid 订单汇总（设备偏好归因）；"
            "晚间占比=18~23点行为占比；高峰小时=活跃行为最集中的小时。"
        ),
        "config": {"new_user_days": c.new_user_days, "devices": list(DEVICE_TYPES)},
        "devices": rows,
    }