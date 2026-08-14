"""渠道分析（开发文档第 28.1 节）。

渠道：organic / search / ads / campaign / recommendation。

指标：用户数、新用户、活跃率、点击率、购买率、GMV、客单价。

口径（明确定义）：
- 用户数：该渠道产生过行为的去重用户；
- 新用户：注册时间在观察周期（默认近 30 天）内、且首次行为落在该渠道的用户；
- 活跃率：渠道活跃用户 / 全渠道活跃用户（占比）；
- 点击率 = click/pv，购买率 = buy/pv（渠道内行为汇总）；
- GMV / 客单价：**渠道质量对比用**，按"该渠道购买用户"的 paid 订单 GMV 汇总，
  因无广告成本字段，不声称真实 ROI，仅作渠道质量对比。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..base import CHANNELS, safe_div


@dataclass(frozen=True)
class ChannelConfig:
    """渠道分析配置。"""

    new_user_days: int = 30     # 新用户判定：注册距今 <= N 天


def channel_analysis(
    users: pd.DataFrame,
    behaviors: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: ChannelConfig | None = None,
) -> dict:
    """按渠道汇总质量指标。

    参数:
        users: users.csv，至少含 user_id / register_time
        behaviors: user_behaviors.csv，至少含 user_id / channel / behavior_type / event_date
        orders: orders.csv，至少含 user_id / total_amount / status
        cfg: 渠道分析配置

    返回:
        dict:
        - definition / config / note（非 ROI 声明）
        - channels: list[{"channel","users","new_users","new_user_ratio",
                          "active_ratio","pv","click","collect","cart","buy",
                          "click_rate","buy_rate","orders","gmv","aov"}]
    """
    cfg = cfg or ChannelConfig()

    beh = behaviors[["user_id", "channel", "behavior_type", "event_date"]].copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh = beh.dropna(subset=["event_date"])
    as_of = beh["event_date"].max()

    reg = users[["user_id", "register_time"]].copy()
    reg["register_time"] = pd.to_datetime(reg["register_time"], errors="coerce").dt.normalize()
    reg = reg.dropna(subset=["register_time"])
    reg["is_new"] = (as_of - reg["register_time"]).dt.days <= cfg.new_user_days
    new_user_ids = set(reg.loc[reg["is_new"], "user_id"])

    # 渠道内指标
    rows = []
    for ch in CHANNELS:
        sub = beh[beh["channel"] == ch]
        users_ch = set(sub["user_id"])
        counts = sub["behavior_type"].value_counts().to_dict()
        pv = int(counts.get("pv", 0))
        click = int(counts.get("click", 0))
        collect = int(counts.get("collect", 0))
        cart = int(counts.get("cart", 0))
        buy = int(counts.get("buy", 0))

        new_users = int(len(users_ch & new_user_ids))
        # GMV：该渠道购买用户的 paid 订单
        buy_users = set(
            sub.loc[sub["behavior_type"] == "buy", "user_id"]
        )
        ch_gmv = orders.loc[
            (orders["status"] == "paid") & (orders["user_id"].isin(buy_users)),
            "total_amount",
        ].sum()
        ch_orders = int(((orders["status"] == "paid") & (orders["user_id"].isin(buy_users))).sum())
        rows.append({
            "channel": ch,
            "users": int(len(users_ch)),
            "new_users": new_users,
            "new_user_ratio": safe_div(new_users, len(users_ch)),
            "active_ratio": safe_div(len(users_ch), beh["user_id"].nunique()),
            "pv": pv,
            "click": click,
            "collect": collect,
            "cart": cart,
            "buy": buy,
            "click_rate": safe_div(click, pv),
            "buy_rate": safe_div(buy, pv),
            "orders": ch_orders,
            "gmv": round(float(ch_gmv), 2),
            "aov": safe_div(ch_gmv, ch_orders),
        })

    rows.sort(key=lambda r: r["gmv"], reverse=True)
    return {
        "definition": (
            "渠道质量对比：用户数=渠道活跃用户；新用户=注册≤{0}天且首次行为落该渠道；"
            "活跃率=渠道用户/全渠道活跃用户；点击率=click/pv；购买率=buy/pv；"
            "GMV/客单价=渠道购买用户的 paid 订单汇总。".format(cfg.new_user_days)
        ),
        "note": "无广告成本字段，本结果仅作渠道质量对比，不声称真实 ROI。",
        "config": {"new_user_days": cfg.new_user_days, "channels": list(CHANNELS)},
        "as_of_date": str(as_of.date()),
        "channels": rows,
    }