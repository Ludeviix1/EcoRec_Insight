"""RFM 用户价值分析（开发文档第 22 节）。

口径（明确）：
- R = 最近一次支付订单距分析日的天数（recency，越小越好）；
- F = 分析周期内支付订单数（frequency，越大越好）；
- M = 分析周期内支付金额（monetary，越大越好）。

评分：
- R / F / M 各按可配置分桶映射为 1~5 分；
- ``RFM_score`` = R_score*100 + F_score*10 + M_score（三位复合码）；
- ``rfm_total`` = R_score + F_score + M_score（便于排序）。

分群（默认规则自上而下首个命中，均可配置）：
高价值 / 重要保持 / 潜力 / 一般 / 沉睡 / 流失风险。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .base import safe_div

# ---- 默认评分分桶（可配置）----
# R：距上次购买天数 <30→5, <60→4, <90→3, <120→2, 其余→1
DEFAULT_R_BINS: tuple = (30, 60, 90, 120)
# F：购买次数 >=8→5, >=4→4, >=2→3, >=1→2, 0→1
DEFAULT_F_BINS: tuple = (1, 2, 4, 8)
# M：金额 >=8000→5, >=3000→4, >=1000→3, >=500→2, 其余→1
DEFAULT_M_BINS: tuple = (500, 1000, 3000, 8000)

# 默认分群规则（首个命中生效）
DEFAULT_SEGMENT_RULES: tuple = (
    {"segment": "高价值", "r_min": 4, "f_min": 4, "m_min": 4},
    {"segment": "重要保持", "r_min": 4, "f_min": 3, "m_min": 3},
    {"segment": "潜力", "r_min": 4, "f_min": 2, "m_min": 2},
    {"segment": "一般", "r_min": 3, "f_min": 2, "m_min": 2},
    {"segment": "沉睡", "r_min": 2, "r_max": 2, "f_min": 2},
    {"segment": "流失风险"},  # 兜底
)


@dataclass(frozen=True)
class RfmConfig:
    """RFM 分析配置（评分规则可配置，开发文档第 22 节）。"""

    as_of_date: str | None = None    # 分析日，默认取支付订单最大日期
    period_days: int = 90            # F/M 分析周期（天）
    r_bins: tuple = DEFAULT_R_BINS
    f_bins: tuple = DEFAULT_F_BINS
    m_bins: tuple = DEFAULT_M_BINS
    segment_rules: tuple = DEFAULT_SEGMENT_RULES


def rfm_analysis(orders: pd.DataFrame, cfg: RfmConfig | None = None) -> dict:
    """对支付用户计算 R/F/M 评分并分群。

    参数:
        orders: data/processed/orders.csv，至少含 user_id / order_time / total_amount / status
        cfg: RFM 配置（评分分桶与分群规则，默认使用内置默认值）

    返回:
        dict:
        - definition: R / F / M 口径说明
        - scoring: 实际使用的分桶与分群规则
        - total_buying_users / segment_distribution / score_distribution
        - users: list[{"user_id","recency_days","purchase_count","total_amount",
                       "r_score","f_score","m_score","rfm_score","rfm_total","segment"}]
    """
    cfg = cfg or RfmConfig()

    paid = orders[orders["status"] == "paid"].copy()
    paid["order_time"] = pd.to_datetime(paid["order_time"], errors="coerce")
    paid = paid.dropna(subset=["order_time"])

    as_of = pd.to_datetime(cfg.as_of_date) if cfg.as_of_date else paid["order_time"].max()
    period_start = as_of - pd.Timedelta(days=cfg.period_days)

    # 每个用户的 R（距上次购买天数）基于全部支付订单
    last_buy = paid.groupby("user_id")["order_time"].max().rename("last_buy_time")
    recency = (as_of - last_buy).dt.days.rename("recency_days").reset_index()

    # F / M 基于分析周期内支付订单
    in_period = paid[paid["order_time"] >= period_start]
    freq = in_period.groupby("user_id").size().rename("purchase_count")
    monet = in_period.groupby("user_id")["total_amount"].sum().rename("total_amount")

    df = recency.merge(freq.reset_index(), on="user_id", how="left")
    df = df.merge(monet.reset_index(), on="user_id", how="left")
    df["purchase_count"] = df["purchase_count"].fillna(0)
    df["total_amount"] = df["total_amount"].fillna(0.0)

    df["r_score"] = df["recency_days"].apply(lambda v: _score_low_is_better(v, cfg.r_bins))
    df["f_score"] = df["purchase_count"].apply(lambda v: _score_high_is_better(v, cfg.f_bins))
    df["m_score"] = df["total_amount"].apply(lambda v: _score_high_is_better(v, cfg.m_bins))
    df["rfm_score"] = df["r_score"] * 100 + df["f_score"] * 10 + df["m_score"]
    df["rfm_total"] = df["r_score"] + df["f_score"] + df["m_score"]
    df["segment"] = df.apply(
        lambda r: _segment_of(r["r_score"], r["f_score"], r["m_score"], cfg.segment_rules),
        axis=1,
    )

    users = [
        {
            "user_id": str(r["user_id"]),
            "recency_days": int(r["recency_days"]),
            "purchase_count": int(r["purchase_count"]),
            "total_amount": round(float(r["total_amount"]), 2),
            "r_score": int(r["r_score"]),
            "f_score": int(r["f_score"]),
            "m_score": int(r["m_score"]),
            "rfm_score": int(r["rfm_score"]),
            "rfm_total": int(r["rfm_total"]),
            "segment": r["segment"],
        }
        for r in df.sort_values("rfm_total", ascending=False).to_dict("records")
    ]

    seg_dist = [
        {
            "segment": s,
            "count": int((df["segment"] == s).sum()),
            "gmv": round(float(df.loc[df["segment"] == s, "total_amount"].sum()), 2),
            "ratio": safe_div(int((df["segment"] == s).sum()), len(df)),
        }
        for s in _ordered_segments(cfg.segment_rules)
    ]

    score_dist = {
        col: [
            {"score": sc, "count": int((df[col] == sc).sum())}
            for sc in (1, 2, 3, 4, 5)
        ]
        for col in ("r_score", "f_score", "m_score")
    }

    return {
        "definition": {
            "R": "最近一次支付订单距分析日天数（天）",
            "F": "分析周期内支付订单数（次）",
            "M": "分析周期内支付金额（元）",
            "period_days": cfg.period_days,
            "as_of_date": str(as_of.date()),
            "scoring_scale": "1~5 分，RFM_score = R*100 + F*10 + M",
        },
        "scoring": {
            "r_bins": list(cfg.r_bins),
            "f_bins": list(cfg.f_bins),
            "m_bins": list(cfg.m_bins),
            "segment_rules": list(cfg.segment_rules),
        },
        "total_buying_users": int(len(df)),
        "segment_distribution": [s for s in seg_dist if s["count"] > 0],
        "score_distribution": score_dist,
        "users": users,
    }


def _score_low_is_better(value, bins) -> int:
    """值越小分越高：value< bins[0]→5, <bins[1]→4, ... 其余→1。"""
    for i, b in enumerate(bins):
        if value < b:
            return len(bins) - i + 1
    return 1


def _score_high_is_better(value, bins) -> int:
    """值越大分越高：命中分桶越多分越高（>=8→5, >=4→4, ... 低于 bins[0]→1）。"""
    return min(1 + sum(1 for b in bins if value >= b), len(bins) + 1)


def _segment_of(r: int, f: int, m: int, rules: tuple) -> str:
    """按规则自上而下匹配，首个命中生效；无命中返回兜底规则（默认 流失风险）。"""
    for rule in rules:
        if _rule_hit(r, f, m, rule):
            return rule["segment"]
    if rules:
        return rules[-1]["segment"]
    return "流失风险"


def _rule_hit(r: int, f: int, m: int, rule: dict) -> bool:
    for k, lo in (("r_min", r), ("f_min", f), ("m_min", m)):
        if k in rule and lo < rule[k]:
            return False
    for k, hi in (("r_max", r), ("f_max", f), ("m_max", m)):
        if k in rule and hi > rule[k]:
            return False
    return True


def _ordered_segments(rules: tuple) -> list[str]:
    seen: list[str] = []
    for r in rules:
        if r["segment"] not in seen:
            seen.append(r["segment"])
    return seen
