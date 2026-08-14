"""DAU / WAU / MAU 分析（开发文档第 16.2 节）。

DAU = 当日产生至少一次行为的用户数；WAU = 当周产生行为的去重用户数；
MAU = 当月产生行为的去重用户数。
"""

from __future__ import annotations

import pandas as pd


def dau_wau_mau(behaviors: pd.DataFrame) -> dict:
    """按日 / 周 / 月统计活跃用户并给出趋势。

    参数:
        behaviors: user_behaviors，至少含 user_id / event_date

    返回:
        dict:
        - dau: list[{"date","dau"}]
        - wau: list[{"date","wau"}]
        - mau: list[{"date","mau"}]
        - latest_dau / latest_wau / latest_mau: 最近一个窗口数值
    """
    df = behaviors[["user_id", "event_date"]].copy()
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df = df.dropna(subset=["event_date"])

    dau = (
        df.groupby(df["event_date"].dt.normalize())
        .nunique()["user_id"]
    )
    dau = dau.reset_index()
    dau.columns = ["ts", "dau"]

    # 周：ISO 周一为一周起点
    wdf = df.copy()
    wdf["week_start"] = wdf["event_date"].dt.to_period("W").apply(lambda r: r.start_time)
    wau = wdf.groupby("week_start").nunique()["user_id"]
    wau = wau.reset_index()
    wau.columns = ["ts", "wau"]

    # 月
    mdf = df.copy()
    mdf["month"] = mdf["event_date"].dt.to_period("M")
    mau = mdf.groupby("month").nunique()["user_id"]
    mau = mau.reset_index()
    mau.columns = ["ts", "mau"]

    def _records(frame: pd.DataFrame, ts_col: str, val_col: str) -> list[dict]:
        return [
            {"date": str(ts.date() if hasattr(ts, "date") else ts), "value": int(v)}
            for ts, v in zip(frame[ts_col], frame[val_col])
        ]

    return {
        "dau": _records(dau, "ts", "dau"),
        "wau": _records(wau, "ts", "wau"),
        "mau": _records(mau, "ts", "mau"),
        "latest_dau": int(dau["dau"].iloc[-1]) if len(dau) else 0,
        "latest_wau": int(wau["wau"].iloc[-1]) if len(wau) else 0,
        "latest_mau": int(mau["mau"].iloc[-1]) if len(mau) else 0,
    }