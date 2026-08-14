"""用户行为分析（开发文档第 16.3 节）。

统计 PV / Click / Collect / Cart / Buy 及各行为转化率。
点击率 = click/pv，收藏率 = collect/pv，加购率 = cart/pv，购买率 = buy/pv。
"""

from __future__ import annotations

import pandas as pd

from ..base import BEHAVIOR_TYPES, FUNNEL_STAGES, safe_div


def behavior_analysis(behaviors: pd.DataFrame) -> dict:
    """按行为类型统计次数与转化率，并给出按日的行为趋势。

    参数:
        behaviors: user_behaviors，至少含 behavior_type / event_date

    返回:
        dict:
        - counts: {behavior_type: count}
        - total: 总行为数
        - rates: click_rate / collect_rate / cart_rate / buy_rate
        - daily_trend: list[{"date","pv","click","collect","cart","buy"}]
    """
    counts: dict[str, int] = {}
    for bt in BEHAVIOR_TYPES:
        counts[bt] = int((behaviors["behavior_type"] == bt).sum())

    total = int(len(behaviors))
    pv = counts.get("pv", 0)

    rates = {
        "click_rate": safe_div(counts.get("click", 0), pv),
        "collect_rate": safe_div(counts.get("collect", 0), pv),
        "cart_rate": safe_div(counts.get("cart", 0), pv),
        "buy_rate": safe_div(counts.get("buy", 0), pv),
    }

    daily_trend = _daily_trend(behaviors)
    return {
        "total": total,
        "counts": counts,
        "rates": rates,
        "daily_trend": daily_trend,
    }


def _daily_trend(behaviors: pd.DataFrame) -> list[dict]:
    """按日统计各行为类型次数，缺失类型补 0。"""
    df = behaviors[["behavior_type", "event_date"]].copy()
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["event_date"])
    if df.empty:
        return []
    pivot = (
        df.groupby(["event_date", "behavior_type"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=list(FUNNEL_STAGES), fill_value=0)
        .sort_index()
    )
    return [
        {"date": str(ts.date()), **{bt: int(pivot.loc[ts, bt]) for bt in FUNNEL_STAGES}}
        for ts in pivot.index
    ]