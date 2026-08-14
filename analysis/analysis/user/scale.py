"""用户规模分析（开发文档第 16.1 节）。

指标：总用户 / 新增用户 / 活跃用户 / 购买用户 / 付费率。
"""

from __future__ import annotations

import pandas as pd

from ..base import safe_div


def user_scale(users: pd.DataFrame, behaviors: pd.DataFrame) -> dict:
    """计算用户规模指标。

    参数:
        users: data/processed/users.csv，至少含 user_id / register_time / gender / city
        behaviors: data/processed/user_behaviors.csv，至少含 user_id / behavior_type

    返回:
        结构化 dict（可直接 JSON 序列化），含：
        total_users / new_users / active_users / buying_users / pay_rate /
        register_trend / gender_distribution / city_distribution
    """
    total_users = int(len(users))
    new_users = int(users["user_id"].nunique())

    reg = pd.to_datetime(users["register_time"], errors="coerce")
    active_users = int(behaviors["user_id"].nunique())
    buying_users = int(behaviors.loc[behaviors["behavior_type"] == "buy", "user_id"].nunique())

    tmp = users[["user_id", "register_time"]].copy()
    tmp["_reg_date"] = reg.where(reg.notna()).dt.date
    reg_trend = (
        tmp.dropna(subset=["_reg_date"])
        .groupby("_reg_date")
        .size()
        .sort_index()
    )

    return {
        "total_users": total_users,
        "new_users": new_users,
        "active_users": active_users,
        "buying_users": buying_users,
        "pay_rate": safe_div(buying_users, active_users),   # 购买用户 / 活跃用户
        "register_trend": [
            {"date": str(d), "count": int(c)} for d, c in reg_trend.items()
        ],
        "gender_distribution": _value_counts(users, "gender"),
        "city_distribution": _value_counts(users, "city"),
    }


def _value_counts(df: pd.DataFrame, col: str) -> list[dict]:
    if col not in df.columns or df[col].isna().all():
        return []
    return [
        {"label": str(k), "count": int(v)}
        for k, v in df[col].fillna("未知").value_counts().items()
    ]