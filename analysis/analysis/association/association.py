"""商品关联规则分析（开发文档第 26 节）。

输入：order_id -> item_id 集合（仅 paid 订单）；
算法：Apriori（mlxtend）→ 频繁项集 → 关联规则；
指标：Support / Confidence / Lift。

口径（明确定义）：
- 事务 = 一张 paid 订单内去重后的商品（或商品分类）集合；
- 输出两个级别：
    * ``item_rules``：商品级规则（文档第 26 节主口径）；
    * ``category_rules``：分类级规则（商品长尾、商品级稀疏时的补充视角）；
- 规则指标：support(A→B)、confidence(A→B)、lift(A→B)；
- 规则来自真实生成的数据，不做人工编造；若某级无规则则如实返回空列表。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from mlxtend.frequent_patterns import association_rules, apriori


@dataclass(frozen=True)
class AssociationConfig:
    """关联规则分析配置。"""

    min_support: float = 0.001     # 最小支持度
    min_confidence: float = 0.03   # 最小置信度（模拟数据组合购买稀疏，阈值需偏低）
    min_lift: float = 1.0          # 最小提升度
    top_n: int = 20                # 每级输出规则数（按 lift 降序）


def association_analysis(
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    items: pd.DataFrame,
    cfg: AssociationConfig | None = None,
) -> dict:
    """挖掘商品级与分类级关联规则。

    参数:
        order_items: order_items.csv，至少含 order_id / item_id
        orders: orders.csv，至少含 order_id / status（过滤 paid）
        items: items.csv，至少含 item_id / item_name / category_id
        cfg: 关联规则配置

    返回:
        dict:
        - definition / config
        - total_orders
        - item_rules: list[{antecedents,consequents,support,confidence,lift,count}]
        - category_rules: list[同上，分类名]
        - item_rules_count / category_rules_count
    """
    cfg = cfg or AssociationConfig()

    paid_ids = orders.loc[orders["status"] == "paid", "order_id"].unique()
    oi = order_items[order_items["order_id"].isin(paid_ids)][["order_id", "item_id"]]
    oi = oi.drop_duplicates()  # 一张订单内同商品去重
    total_orders = int(oi["order_id"].nunique())

    name_map = dict(zip(items["item_id"], items["item_name"]))
    cat_map = dict(zip(items["item_id"], items["category_id"]))
    cat_name = {cid: f"分类{cid}" for cid in items["category_id"].dropna().unique()}

    def _transactions(col: str) -> pd.DataFrame:
        return (
            pd.get_dummies(oi.set_index("order_id")[col], prefix="", prefix_sep="")
            .groupby(level=0)
            .max()
        )

    def _rules(trans: pd.DataFrame, label_map: dict, cfg2: AssociationConfig) -> list:
        if trans.empty or len(trans.columns) < 2:
            return []
        freq = apriori(trans, min_support=cfg2.min_support, use_colnames=True, max_len=2)
        if freq.empty:
            return []
        rules = association_rules(freq, metric="lift", min_threshold=cfg2.min_lift)
        rules = rules[(rules["confidence"] >= cfg2.min_confidence) &
                      (rules["support"] >= cfg2.min_support)]
        out = []
        for r in rules.sort_values("lift", ascending=False).head(cfg2.top_n).to_dict("records"):
            ants = sorted({label_map.get(i, str(i)) for i in r["antecedents"]})
            cons = sorted({label_map.get(i, str(i)) for i in r["consequents"]})
            out.append({
                "antecedents": ants,
                "consequents": cons,
                "support": round(float(r["support"]), 4),
                "confidence": round(float(r["confidence"]), 4),
                "lift": round(float(r["lift"]), 4),
                "count": int(round(r["support"] * total_orders)),
            })
        return out

    item_rules = _rules(_transactions("item_id"), name_map, cfg)
    # 分类级：order -> category_id 集合
    oi_cat = oi.merge(items[["item_id", "category_id"]].dropna(subset=["category_id"]),
                      on="item_id", how="inner")
    category_rules = []
    if not oi_cat.empty:
        trans_cat = (
            pd.get_dummies(oi_cat.set_index("order_id")["category_id"],
                           prefix="", prefix_sep="")
            .groupby(level=0)
            .max()
        )
        category_rules = _rules(trans_cat, cat_name, cfg)

    return {
        "definition": (
            "事务=paid 订单内去重商品（或商品分类）集合；Apriori 挖掘频繁项集→关联规则；"
            "support=同时出现订单占比；confidence=含 A 的订单中出现 B 的比例；"
            "lift=confidence/基准概率（>1 表示正相关）。"
            "商品级为主口径，分类级为长尾补充视角。规则来自真实生成数据。"
        ),
        "config": {
            "min_support": cfg.min_support,
            "min_confidence": cfg.min_confidence,
            "min_lift": cfg.min_lift,
            "top_n": cfg.top_n,
        },
        "total_orders": total_orders,
        "item_rules_count": len(item_rules),
        "category_rules_count": len(category_rules),
        "item_rules": item_rules,
        "category_rules": category_rules,
    }