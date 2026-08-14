"""转化漏斗（开发文档第 19 节）。

标准漏斗：PV → Click → Collect → Cart → Buy。
- step_conversion_rate = 本阶段 / 上一阶段（首阶段为 1.0 或 null）；
- overall_conversion_rate = 本阶段 / PV。
所有除法防除零。
"""

from __future__ import annotations

import pandas as pd

from ..base import FUNNEL_STAGES, safe_div


def conversion_funnel(behaviors: pd.DataFrame) -> dict:
    """按行为类型统计漏斗各阶段次数并计算转化率。

    参数:
        behaviors: user_behaviors，至少含 behavior_type

    返回:
        dict: {"stages": [...], "steps": [{stage,count,step_conversion_rate,
                                            overall_conversion_rate}]}
    """
    counts = {bt: int((behaviors["behavior_type"] == bt).sum()) for bt in FUNNEL_STAGES}
    pv_count = counts["pv"]

    steps = []
    prev = None
    for i, bt in enumerate(FUNNEL_STAGES):
        cur = counts[bt]
        step_rate = 1.0 if i == 0 else safe_div(cur, prev)
        steps.append({
            "stage": bt,
            "count": cur,
            "step_conversion_rate": step_rate,
            "overall_conversion_rate": safe_div(cur, pv_count),
        })
        prev = cur

    return {
        "stages": list(FUNNEL_STAGES),
        "steps": steps,
    }