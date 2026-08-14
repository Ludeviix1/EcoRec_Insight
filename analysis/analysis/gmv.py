"""GMV / 订单 / 客单价 / ARPU 分析（开发文档第 17 节）。

GMV = 有效支付订单金额之和；
客单价 = GMV / 支付订单数；
ARPU = GMV / 活跃用户数。
"""

from __future__ import annotations

import pandas as pd

from .base import ORDER_STATUSES, safe_div


def gmv_analysis(orders: pd.DataFrame, behaviors: pd.DataFrame) -> dict:
    """计算 GMV 类指标并按日 / 周 / 月给出趋势。

    参数:
        orders: data/processed/orders.csv，至少含 order_id / user_id / order_time / total_amount / status
        behaviors: user_behaviors，至少含 user_id / event_date（用于活跃用户数）

    返回:
        dict:
        - gmv_total / order_count / buying_users / active_users
        - aov（客单价）/ arpu / paid_rate
        - status_distribution: {status: count}
        - daily_trend: list[{"date","gmv","orders","buying_users","aov","arpu"}]
        - weekly_trend / monthly_trend: 同上按周/月聚合
    """
    df = orders.copy()
    df["order_time"] = pd.to_datetime(df["order_time"], errors="coerce")
    df = df.dropna(subset=["order_time"])
    df["date"] = df["order_time"].dt.normalize()
    df["week"] = df["order_time"].dt.to_period("W").apply(lambda r: r.start_time)
    df["month"] = df["order_time"].dt.to_period("M")

    paid = df[df["status"] == "paid"]
    gmv_total = float(paid["total_amount"].sum())
    order_count = int(len(paid))
    buying_users = int(paid["user_id"].nunique())
    active_users = int(behaviors["user_id"].nunique())

    def _agg(grp: pd.DataFrame, label_col: str) -> list[dict]:
        rows = []
        for ts, sub in grp:
            sub_gmv = float(sub["total_amount"].sum())
            sub_orders = int(len(sub))
            sub_buying = int(sub["user_id"].nunique())
            rows.append({
                "date": str(ts.date() if hasattr(ts, "date") else ts),
                "gmv": round(sub_gmv, 2),
                "orders": sub_orders,
                "buying_users": sub_buying,
                "aov": safe_div(sub_gmv, sub_orders),
                "arpu": safe_div(sub_gmv, active_users, scale=4),
            })
        return rows

    status_dist = {s: int((df["status"] == s).sum()) for s in ORDER_STATUSES}

    return {
        "gmv_total": round(gmv_total, 2),
        "order_count": order_count,
        "buying_users": buying_users,
        "active_users": active_users,
        "aov": safe_div(gmv_total, order_count),
        "arpu": safe_div(gmv_total, active_users, scale=4),
        "paid_rate": safe_div(buying_users, active_users),
        "status_distribution": status_dist,
        "daily_trend": _agg(paid.groupby("date"), "date"),
        "weekly_trend": _agg(paid.groupby("week"), "week"),
        "monthly_trend": _agg(paid.groupby("month"), "month"),
    }