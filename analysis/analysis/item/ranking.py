"""商品 / 分类 / 品牌排行（开发文档第 18 节）。

全部函数输入 processed CSV 的 DataFrame，输出可直接 JSON 序列化的 dict。
"""

from __future__ import annotations

import pandas as pd

from ..base import BEHAVIOR_TYPES, safe_div

# 商品行为权重（开发文档第 35.2 节），用于综合热门分排序
_BEHAVIOR_WEIGHTS: dict[str, int] = {"pv": 1, "click": 2, "collect": 3, "cart": 4, "buy": 5}


def item_ranking(
    items: pd.DataFrame,
    behaviors: pd.DataFrame,
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    top_n: int = 10,
) -> dict:
    """商品排行：行为统计 + GMV + 唯一用户 + 转化率，按综合热门分降序。

    参数:
        items: items.csv，含 item_id / item_name / category_id / brand / price / status
        behaviors: user_behaviors.csv，含 item_id / user_id / behavior_type
        order_items: order_items.csv，含 item_id / amount
        orders: orders.csv，含 order_id / status（过滤 paid）
        top_n: 返回条数

    返回:
        dict: {"items": [{item_id,item_name,category_id,brand,price,status,
                          pv,click,collect,cart,buy,gmv,unique_users,
                          conversion_rate,heat_score}], "total": n}
    """
    # 商品维度信息
    dim = items[["item_id", "item_name", "category_id", "brand", "price", "status"]].copy()
    dim["price"] = pd.to_numeric(dim["price"], errors="coerce")

    # 行为计数
    beh = behaviors.groupby(["item_id", "behavior_type"]).size().unstack(fill_value=0)
    for bt in BEHAVIOR_TYPES:
        if bt not in beh.columns:
            beh[bt] = 0
    beh = beh[list(BEHAVIOR_TYPES)]

    # 唯一用户
    uv = behaviors.groupby("item_id")["user_id"].nunique().rename("unique_users")

    # GMV：仅 paid 订单的明细金额
    paid_ids = orders.loc[orders["status"] == "paid", "order_id"].unique()
    oi = order_items[order_items["order_id"].isin(paid_ids)]
    gmv = oi.groupby("item_id")["amount"].sum().rename("gmv")

    table = dim.join(beh, on="item_id").join(uv, on="item_id").join(gmv, on="item_id")
    table["gmv"] = pd.to_numeric(table["gmv"], errors="coerce").fillna(0.0)
    table["unique_users"] = table["unique_users"].fillna(0).astype(int)
    table["pv"] = table["pv"].fillna(0).astype(int)
    table["click"] = table["click"].fillna(0).astype(int)
    table["collect"] = table["collect"].fillna(0).astype(int)
    table["cart"] = table["cart"].fillna(0).astype(int)
    table["buy"] = table["buy"].fillna(0).astype(int)

    # 转化率 = buy / pv；综合热度分 = Σ 行为权重 * 次数 + gmv/100
    table["conversion_rate"] = [
        safe_div(b, p) for b, p in zip(table["buy"], table["pv"])
    ]
    table["heat_score"] = (
        sum(w * table[bt] for bt, w in _BEHAVIOR_WEIGHTS.items())
        + table["gmv"] / 100.0
    )

    table = table.sort_values("heat_score", ascending=False).head(top_n)

    records = table.reset_index().to_dict("records")
    items_out = []
    for r in records:
        items_out.append({
            "item_id": r["item_id"],
            "item_name": str(r["item_name"]),
            "category_id": r["category_id"],
            "brand": r["brand"] if pd.notna(r["brand"]) else None,
            "price": round(float(r["price"]), 2) if pd.notna(r["price"]) else None,
            "status": int(r["status"]) if pd.notna(r["status"]) else None,
            "pv": int(r["pv"]),
            "click": int(r["click"]),
            "collect": int(r["collect"]),
            "cart": int(r["cart"]),
            "buy": int(r["buy"]),
            "gmv": round(float(r["gmv"]), 2),
            "unique_users": int(r["unique_users"]),
            "conversion_rate": round(float(r["conversion_rate"]), 4),
            "heat_score": round(float(r["heat_score"]), 2),
        })

    return {"total": int(len(table)), "items": items_out}


def category_ranking(
    items: pd.DataFrame,
    behaviors: pd.DataFrame,
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    top_n: int = 10,
) -> dict:
    """分类排行：用户数 / PV / 点击 / 收藏 / 加购 / 购买 / 订单 / GMV / 转化率。

    分类维度以 items 为准（保证无行为的分类也能通过 GMV 进入排行）。
    """
    dim = items[["item_id", "category_id"]].dropna(subset=["category_id"])
    categories = pd.DataFrame({"category_id": sorted(dim["category_id"].unique())})

    beh = behaviors.merge(dim, on="item_id", how="inner")
    beh_counts = (
        beh.groupby(["category_id", "behavior_type"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for bt in BEHAVIOR_TYPES:
        if bt not in beh_counts.columns:
            beh_counts[bt] = 0
    beh_counts = beh_counts[["category_id"] + list(BEHAVIOR_TYPES)]

    users = beh.groupby("category_id")["user_id"].nunique().rename("users").reset_index()

    paid_ids = orders.loc[orders["status"] == "paid", "order_id"].unique()
    oi = order_items[order_items["order_id"].isin(paid_ids)].merge(dim, on="item_id", how="inner")
    gmv = oi.groupby("category_id")["amount"].sum().rename("gmv").reset_index()
    orders_cnt = oi.groupby("category_id")["order_id"].nunique().rename("orders").reset_index()

    table = (
        categories
        .merge(beh_counts, on="category_id", how="left")
        .merge(users, on="category_id", how="left")
        .merge(gmv, on="category_id", how="left")
        .merge(orders_cnt, on="category_id", how="left")
    )
    table["gmv"] = pd.to_numeric(table["gmv"], errors="coerce").fillna(0.0)
    table["orders"] = table["orders"].fillna(0).astype(int)
    table["users"] = table["users"].fillna(0).astype(int)
    for bt in BEHAVIOR_TYPES:
        table[bt] = pd.to_numeric(table[bt], errors="coerce").fillna(0).astype(int)
    table["conversion_rate"] = [
        safe_div(b, p) for b, p in zip(table["buy"], table["pv"])
    ]
    table = table.sort_values("gmv", ascending=False).head(top_n)

    return {
        "total": int(len(table)),
        "categories": [
            {
                "category_id": r["category_id"],
                "users": int(r["users"]),
                "pv": int(r["pv"]),
                "click": int(r["click"]),
                "collect": int(r["collect"]),
                "cart": int(r["cart"]),
                "buy": int(r["buy"]),
                "orders": int(r["orders"]),
                "gmv": round(float(r["gmv"]), 2),
                "conversion_rate": round(float(r["conversion_rate"]), 4),
            }
            for r in table.to_dict("records")
        ],
    }


def brand_ranking(
    items: pd.DataFrame,
    behaviors: pd.DataFrame,
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    top_n: int = 10,
) -> dict:
    """品牌排行：销量(quantity) / GMV / 用户数 / 复购用户 / 客单价。"""
    dim = items[["item_id", "brand"]].copy().dropna(subset=["brand"])

    beh = behaviors.merge(dim, on="item_id", how="inner")
    users = beh.groupby("brand")["user_id"].nunique().rename("users")

    paid_ids = orders.loc[orders["status"] == "paid", "order_id"].unique()
    paid_orders = orders[orders["order_id"].isin(paid_ids)][["order_id", "user_id"]]
    oi = (
        order_items[order_items["order_id"].isin(paid_ids)]
        .merge(dim, on="item_id", how="inner")
        .merge(paid_orders, on="order_id", how="inner")
    )
    oi = oi.copy()
    oi["quantity"] = pd.to_numeric(oi["quantity"], errors="coerce").fillna(0)

    gmv = oi.groupby("brand")["amount"].sum().rename("gmv")
    sold = oi.groupby("brand")["quantity"].sum().rename("sold")
    buy_users = oi.groupby("brand")["user_id"].nunique().rename("buy_users")
    orders_cnt = oi.groupby("brand")["order_id"].nunique().rename("orders")

    table = gmv.to_frame().join(sold).join(buy_users).join(orders_cnt).join(users)
    table["gmv"] = pd.to_numeric(table["gmv"], errors="coerce").fillna(0.0)
    table["sold"] = pd.to_numeric(table["sold"], errors="coerce").fillna(0)
    table["buy_users"] = table["buy_users"].fillna(0).astype(int)
    table["orders"] = table["orders"].fillna(0).astype(int)
    table["users"] = table["users"].fillna(0).astype(int)
    table["aov"] = [safe_div(g, o) for g, o in zip(table["gmv"], table["orders"])]
    table = table.sort_values("gmv", ascending=False).head(top_n)

    records = table.reset_index().to_dict("records")
    return {
        "total": int(len(table)),
        "brands": [
            {
                "brand": r["brand"],
                "gmv": round(float(r["gmv"]), 2),
                "sold": float(r["sold"]),
                "buy_users": int(r["buy_users"]),
                "orders": int(r["orders"]),
                "users": int(r["users"]),
                "aov": round(float(r["aov"]), 2),
            }
            for r in records
        ],
    }