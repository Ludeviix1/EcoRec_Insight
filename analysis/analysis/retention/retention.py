"""用户留存分析（开发文档第 20.1 节）。

留存口径（明确）：
- cohort 起点 = 用户首次活跃日期（首次行为日期）；
- 次日留存 = 首次活跃次日仍产生行为的用户占 cohort 的比例；
- 3/7/14/30 日留存同理（按 cohort 计算，整体为 cohort 规模加权）。
"""

from __future__ import annotations

import pandas as pd

from ..base import safe_div
from ..cohort import RETENTION_OFFSETS, cohort_analysis

# 留存周期 -> 中文标签
RETENTION_LABELS: dict[int, str] = {
    1: "次日",
    3: "3日",
    7: "7日",
    14: "14日",
    30: "30日",
}


def retention_analysis(
    behaviors: pd.DataFrame,
    *,
    offsets: tuple[int, ...] = RETENTION_OFFSETS,
) -> dict:
    """计算各留存周期整体留存率，并按 cohort 给出明细。

    参数:
        behaviors: user_behaviors，至少含 user_id / event_date
        offsets: 留存周期列表（天）

    返回:
        dict:
        - definition: 留存口径说明
        - offsets: 留存周期列表
        - overall: list[{"offset","label","rate","base","retained"}]
        - by_cohort: 复用 cohort 明细（cohort_date × 各日留存率）
    """
    c = cohort_analysis(behaviors, offsets=offsets)

    overall = []
    for d in offsets:
        total_retained = sum(r[f"day_{d}"] for r in c["cohorts"])
        total_base = sum(r["day_0"] for r in c["cohorts"])
        overall.append({
            "offset": int(d),
            "label": RETENTION_LABELS.get(int(d), f"{d}日"),
            "rate": safe_div(total_retained, total_base),
            "base": int(total_base),
            "retained": int(total_retained),
        })

    by_cohort = [
        {
            "cohort_date": r["cohort_date"],
            "size": r["day_0"],
            **{f"rate_day_{d}": r[f"rate_day_{d}"] for d in offsets},
        }
        for r in c["cohorts"]
    ]

    return {
        "definition": (
            "留存口径：以用户首次活跃日期为 cohort 起点；"
            "第 N 日留存 = cohort 中首次活跃后第 N 天仍产生行为的用户数 / cohort 规模。"
        ),
        "offsets": list(offsets),
        "overall": overall,
        "by_cohort": by_cohort,
    }
