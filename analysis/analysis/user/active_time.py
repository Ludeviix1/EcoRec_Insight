"""活跃时间分析（开发文档第 16.4 节）。

按 hour / weekday / device 统计行为量，回答用户什么时候最活跃。
"""

from __future__ import annotations

import pandas as pd

from ..base import DEVICE_TYPES


def active_time(behaviors: pd.DataFrame) -> dict:
    """按小时、星期、设备统计行为分布。

    参数:
        behaviors: user_behaviors，至少含 behavior_type / event_date / event_hour / device_type

    返回:
        dict:
        - by_hour: list[{"hour","pv","buy","total"}]（0-23）
        - by_weekday: list[{"weekday","count"}]（0=周一）
        - by_device_hour: list[{"device","hour","count"}]
    """
    df = behaviors[["behavior_type", "event_date", "event_hour", "device_type"]].copy()
    df["event_hour"] = pd.to_numeric(df["event_hour"], errors="coerce")
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df = df.dropna(subset=["event_hour", "event_date"])
    df["hour"] = df["event_hour"].astype(int)
    df["weekday"] = df["event_date"].dt.weekday

    # 按小时：total + 购买次数
    hour_records = []
    for h in range(24):
        sub = df[df["hour"] == h]
        hour_records.append({
            "hour": h,
            "pv": int((sub["behavior_type"] == "pv").sum()),
            "buy": int((sub["behavior_type"] == "buy").sum()),
            "total": int(len(sub)),
        })

    # 按星期（0=周一）
    weekday_records = [
        {"weekday": int(w), "count": int((df["weekday"] == w).sum())}
        for w in range(7)
    ]

    # 按设备 × 小时
    device_hour = (
        df.groupby(["device_type", "hour"])
        .size()
        .reset_index(name="count")
    )
    device_records = []
    for dev in DEVICE_TYPES:
        sub = device_hour[device_hour["device_type"] == dev]
        counts = dict(zip(sub["hour"], sub["count"]))
        device_records.append({
            "device": dev,
            "hours": [{"hour": int(h), "count": int(counts.get(h, 0))} for h in range(24)],
        })

    return {
        "by_hour": hour_records,
        "by_weekday": weekday_records,
        "by_device_hour": device_records,
    }