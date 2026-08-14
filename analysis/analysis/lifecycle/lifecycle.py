"""用户生命周期分析（开发文档第 21 节）。

阶段定义（规则必须配置化，默认自上而下首个命中）：
新用户 / 成长期 / 活跃用户 / 高价值用户 / 沉默用户 / 流失风险。

判定依赖：
- recency_days      距最近一次行为的（日）间隔；
- register_days     距注册日的（日）间隔；
- total_amount      累计支付金额；
- purchase_count    累计支付订单数。

默认规则（LifecycleConfig.rules，可整体替换）：
1. 高价值用户   recency<=7 且 total_amount>=5000；
2. 新用户       register_days<=7；
3. 成长期       register_days<=30 且 purchase_count>=1；
4. 活跃用户     recency<=7；
5. 沉默用户     recency<=30；
6. 流失风险     兜底（recency>30）。

说明：规则示例取自开发文档第 21 节（最近 7 天有行为→活跃、
7~30 天无行为→沉默、30 天以上无行为→流失风险）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..base import safe_div

# 生命周期阶段（顺序与默认规则一致）
LIFECYCLE_STAGES: tuple[str, ...] = (
    "高价值用户", "新用户", "成长期", "活跃用户", "沉默用户", "流失风险",
)

# 默认规则（自上而下首个命中，均可配置）
DEFAULT_LIFECYCLE_RULES: tuple = (
    {"stage": "高价值用户", "recency_days_max": 7, "total_amount_min": 5000},
    {"stage": "新用户", "register_days_max": 7},
    {"stage": "成长期", "register_days_max": 30, "purchase_count_min": 1},
    {"stage": "活跃用户", "recency_days_max": 7},
    {"stage": "沉默用户", "recency_days_max": 30},
    {"stage": "流失风险"},  # 兜底
)


@dataclass(frozen=True)
class LifecycleConfig:
    """生命周期分析配置（规则配置化，开发文档第 21 节）。"""

    as_of_date: str | None = None      # 分析日，默认取行为最大日期
    rules: tuple = DEFAULT_LIFECYCLE_RULES


def lifecycle_analysis(
    users: pd.DataFrame,
    behaviors: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: LifecycleConfig | None = None,
) -> dict:
    """对每个用户判定生命周期阶段。

    参数:
        users: users.csv，至少含 user_id / register_time
        behaviors: user_behaviors.csv，至少含 user_id / event_date
        orders: orders.csv，至少含 user_id / total_amount / status / order_time
        cfg: 生命周期配置（默认规则）

    返回:
        dict:
        - definition: 阶段与规则说明
        - config: 实际使用规则
        - as_of_date
        - distribution: [{stage, count, ratio, gmv, avg_amount}]
        - users: list[{"user_id","register_days","recency_days",
                       "purchase_count","total_amount","stage"}]
    """
    cfg = cfg or LifecycleConfig()

    beh = behaviors[["user_id", "event_date"]].copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh = beh.dropna(subset=["event_date"])
    as_of = pd.to_datetime(cfg.as_of_date) if cfg.as_of_date else beh["event_date"].max()

    last_active = beh.groupby("user_id")["event_date"].max().rename("last_active")

    reg = users[["user_id", "register_time"]].copy()
    reg["register_time"] = pd.to_datetime(reg["register_time"], errors="coerce").dt.normalize()

    paid = orders[orders["status"] == "paid"].copy()
    paid["order_time"] = pd.to_datetime(paid["order_time"], errors="coerce")
    amt = paid.groupby("user_id")["total_amount"].sum().rename("total_amount")
    cnt = paid.groupby("user_id").size().rename("purchase_count")

    base = reg.merge(last_active.reset_index(), on="user_id", how="left")
    base = base.merge(amt.reset_index(), on="user_id", how="left")
    base = base.merge(cnt.reset_index(), on="user_id", how="left")
    base["total_amount"] = base["total_amount"].fillna(0.0)
    base["purchase_count"] = base["purchase_count"].fillna(0).astype(int)

    base["register_days"] = (as_of - base["register_time"]).dt.days
    base["recency_days"] = (as_of - base["last_active"]).dt.days
    base.loc[base["last_active"].isna(), "recency_days"] = 10**9  # 无行为视为流失
    base["recency_days"] = base["recency_days"].fillna(10**9).astype(int)

    base["stage"] = base.apply(
        lambda r: _stage_of(
            int(r["register_days"]), int(r["recency_days"]),
            int(r["purchase_count"]), float(r["total_amount"]),
            cfg.rules,
        ),
        axis=1,
    )

    distribution = []
    for s in _ordered_stages(cfg.rules):
        sub = base[base["stage"] == s]
        distribution.append({
            "stage": s,
            "count": int(len(sub)),
            "ratio": safe_div(len(sub), len(base)),
            "gmv": round(float(sub["total_amount"].sum()), 2),
            "avg_amount": safe_div(sub["total_amount"].sum(), len(sub)),
        })

    users_out = [
        {
            "user_id": str(r["user_id"]),
            "register_days": int(r["register_days"]),
            "recency_days": int(r["recency_days"]),
            "purchase_count": int(r["purchase_count"]),
            "total_amount": round(float(r["total_amount"]), 2),
            "stage": r["stage"],
        }
        for r in base.sort_values(["total_amount", "register_days"], ascending=[False, True])
        .to_dict("records")
    ]

    return {
        "definition": _definition(cfg.rules),
        "config": {"rules": list(cfg.rules), "as_of_date": str(as_of.date())},
        "total_users": int(len(base)),
        "distribution": distribution,
        "users": users_out,
    }


def _stage_of(register_days: int, recency_days: int, purchase_count: int, total_amount: float, rules: tuple) -> str:
    """按配置规则自上而下匹配，首个命中生效；无命中返回兜底规则。"""
    for rule in rules:
        if _rule_hit(register_days, recency_days, purchase_count, total_amount, rule):
            return rule["stage"]
    if rules and "stage" in rules[-1]:
        return rules[-1]["stage"]
    return "流失风险"


def _rule_hit(reg: int, recency: int, purchases: int, amount: float, rule: dict) -> bool:
    for key, val in (
        ("register_days_max", reg), ("recency_days_max", recency),
        ("purchase_count_min", purchases), ("total_amount_min", amount),
    ):
        if key in rule:
            if "min" in key and val < rule[key]:
                return False
            if "max" in key and val > rule[key]:
                return False
    return True


def _ordered_stages(rules: tuple) -> list[str]:
    seen: list[str] = []
    for r in rules:
        if r.get("stage") and r["stage"] not in seen:
            seen.append(r["stage"])
    return seen


def _definition(rules: tuple) -> str:
    parts = []
    for r in rules:
        conds = []
        if "register_days_max" in r:
            conds.append(f"注册≤{r['register_days_max']}天")
        if "recency_days_max" in r:
            conds.append(f"距最近行为≤{r['recency_days_max']}天")
        if "purchase_count_min" in r:
            conds.append(f"支付订单≥{r['purchase_count_min']}")
        if "total_amount_min" in r:
            conds.append(f"累计消费≥{r['total_amount_min']}")
        parts.append(f"{r.get('stage')}：{'且'.join(conds) if conds else '兜底'}")
    return "生命周期判定（自上而下首个命中）：" + "；".join(parts) + "。"