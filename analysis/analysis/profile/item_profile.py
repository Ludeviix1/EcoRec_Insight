"""商品画像 item_profile（开发文档第 5.1 / 25 节）。

每个商品输出画像，包括：
- 基础属性：item_name / category_id / brand / price / stock / status / created_at；
- 行为统计：pv / click / collect / cart / buy / 唯一用户 / 转化率；
- 销售统计：销量(quantity) / 订单数 / GMV；
- 生命周期阶段：复用 itemlife 的判定；
- 价格带：基于全局价格分位；
- 热度分：行为加权热度（与商品排行口径一致）。

说明：画像字段全部可 JSON 序列化。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..base import BEHAVIOR_TYPES, safe_div
from ..itemlife import ItemLifeConfig, item_lifecycle_analysis

# 行为权重（与商品排行保持一致，开发文档第 18 节）
_BEHAVIOR_WEIGHTS: dict[str, int] = {"pv": 1, "click": 2, "collect": 3, "cart": 4, "buy": 5}


@dataclass(frozen=True)
class ItemProfileConfig:
    """商品画像配置。"""

    life_cfg: ItemLifeConfig = ItemLifeConfig()


def item_profile(
    items: pd.DataFrame,
    behaviors: pd.DataFrame,
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: ItemProfileConfig | None = None,
) -> dict:
    """为每个商品生成画像。

    参数:
        items: items.csv，含 item_id / item_name / category_id / brand / price / stock / status / created_at
        behaviors: user_behaviors.csv，含 item_id / user_id / behavior_type
        order_items: order_items.csv，含 order_id / item_id / quantity / amount
        orders: orders.csv，含 order_id / status
        cfg: 画像配置

    返回:
        dict:
        - definition
        - total_items
        - profiles: list[{item_id, 基础属性, 行为统计, 销售统计,
                           生命周期阶段, 价格带, 热度分, 转化率}]
    """
    cfg = cfg or ItemProfileConfig()

    life = item_lifecycle_analysis(items, behaviors, order_items, orders, cfg.life_cfg)
    life_map = {i["item_id"]: i["stage"] for i in life["items"]}

    # 行为统计
    beh = behaviors[["item_id", "user_id", "behavior_type"]].copy()
    bcounts = beh.groupby(["item_id", "behavior_type"]).size().unstack(fill_value=0)
    for bt in BEHAVIOR_TYPES:
        if bt not in bcounts.columns:
            bcounts[bt] = 0
    bcounts = bcounts[list(BEHAVIOR_TYPES)]
    uv = beh.groupby("item_id")["user_id"].nunique().rename("unique_users")

    # 销售统计（仅 paid）
    paid_ids = orders.loc[orders["status"] == "paid", "order_id"].unique()
    oi = order_items[order_items["order_id"].isin(paid_ids)].copy()
    oi["quantity"] = pd.to_numeric(oi["quantity"], errors="coerce").fillna(0)
    sold = oi.groupby("item_id")["quantity"].sum().rename("sold")
    ocount = oi.groupby("item_id")["order_id"].nunique().rename("orders")
    gmv = oi.groupby("item_id")["amount"].sum().rename("gmv")

    # 价格带（全局分位）
    prices = pd.to_numeric(items["price"], errors="coerce")
    q1, q3 = prices.quantile(0.25), prices.quantile(0.75)

    dim = items.copy()
    dim = dim.join(bcounts, on="item_id").join(uv, on="item_id")
    dim = dim.join(sold, on="item_id").join(ocount, on="item_id").join(gmv, on="item_id")

    profiles = []
    for r in dim.to_dict("records"):
        iid = r["item_id"]
        pv = int(r["pv"]) if pd.notna(r["pv"]) else 0
        buy = int(r["buy"]) if pd.notna(r["buy"]) else 0
        price = float(r["price"]) if pd.notna(r["price"]) else 0.0
        heat = sum(w * (int(r[bt]) if pd.notna(r[bt]) else 0) for bt, w in _BEHAVIOR_WEIGHTS.items())

        profile = {
            "item_id": iid,
            "item_name": str(r["item_name"]),
            "basic": {
                "category_id": r["category_id"] if pd.notna(r["category_id"]) else None,
                "brand": r["brand"] if pd.notna(r["brand"]) else None,
                "price": round(price, 2),
                "stock": int(r["stock"]) if pd.notna(r["stock"]) else None,
                "status": int(r["status"]) if pd.notna(r["status"]) else None,
                "created_at": str(r["created_at"]) if pd.notna(r["created_at"]) else None,
            },
            "behavior": {
                "pv": pv,
                "click": int(r["click"]) if pd.notna(r["click"]) else 0,
                "collect": int(r["collect"]) if pd.notna(r["collect"]) else 0,
                "cart": int(r["cart"]) if pd.notna(r["cart"]) else 0,
                "buy": buy,
                "unique_users": int(r["unique_users"]) if pd.notna(r["unique_users"]) else 0,
                "conversion_rate": safe_div(buy, pv),
            },
            "sales": {
                "sold": float(r["sold"]) if pd.notna(r["sold"]) else 0.0,
                "orders": int(r["orders"]) if pd.notna(r["orders"]) else 0,
                "gmv": round(float(r["gmv"]) if pd.notna(r["gmv"]) else 0.0, 2),
            },
            "lifecycle_stage": life_map.get(iid),
            "price_band": _price_band(price, q1, q3),
            "heat_score": round(float(heat), 2),
        }
        profiles.append(profile)

    return {
        "definition": (
            "每商品画像：基础属性/行为统计/销售统计/生命周期阶段/价格带/热度分。"
            "生命周期复用 itemlife 模块；热度分=Σ行为权重×次数；价格带按全局分位。"
        ),
        "total_items": int(len(dim)),
        "profiles": profiles,
    }


def _price_band(price: float, q1: float, q3: float) -> str:
    if price <= 0:
        return "免费/无效"
    if price <= q1:
        return "低价带"
    if price <= q3:
        return "中价带"
    return "高价带"