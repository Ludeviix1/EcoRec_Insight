"""价格分析（开发文档第 27 节）。

按商品价格自动分箱，分析：价格区间 → 点击/加购/购买率 → GMV；
以及价格 vs 购买频率 / 价格 vs 用户价值 / 价格 vs 转化率。

口径（明确定义）：
- 价格以 items.price 为准；分箱自动（默认 pd.qcut 等频 5 箱，冲突时退化为等宽）；
- 行为率按区间内所有商品的 pv/click/cart/buy 汇总计算；
- GMV 仅统计 paid 订单明细；
- 购买频率 = 区间内购买用户的人均购买订单数；
- 用户价值 = 区间内购买用户的人均 GMV。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..base import safe_div


@dataclass(frozen=True)
class PriceConfig:
    """价格分析配置。"""

    n_bins: int = 5                     # 价格分箱数量（自动分箱）
    top_n: int = 5                      # 观察区间数量（默认全部）


def price_analysis(
    items: pd.DataFrame,
    behaviors: pd.DataFrame,
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: PriceConfig | None = None,
) -> dict:
    """价格区间漏斗 + 价格 vs 购买频率 / 用户价值 / 转化率。

    参数:
        items: items.csv，至少含 item_id / price
        behaviors: user_behaviors.csv，至少含 item_id / behavior_type / user_id
        order_items: order_items.csv，至少含 order_id / item_id / amount
        orders: orders.csv，至少含 order_id / status / user_id
        cfg: 价格分析配置

    返回:
        dict:
        - definition / config
        - price_bins: list[{"bin_label","price_min","price_max","item_count",
                            "pv","click","cart","buy","click_rate","cart_rate",
                            "buy_rate","orders","gmv","buy_users","buy_freq","user_value"}]
        - cross: 价格 vs 转化/频率/价值 相关性（Spearman/Pearson 用数字近似）
    """
    cfg = cfg or PriceConfig()

    dim = items[["item_id", "price"]].copy()
    dim["price"] = pd.to_numeric(dim["price"], errors="coerce")
    dim = dim.dropna(subset=["price"])

    # ---- 自动分箱（等频 -> 冲突退化等宽）----
    bin_label, edges = _auto_bin(dim["price"], cfg.n_bins)
    dim["bin"] = dim["price"].map(lambda p: _assign_bin(p, edges, bin_label))

    # ---- 行为率 ----
    beh = behaviors[["item_id", "user_id", "behavior_type"]].copy()
    beh = beh.merge(dim[["item_id", "bin"]], on="item_id", how="inner")
    rates = beh.groupby(["bin", "behavior_type"]).size().unstack(fill_value=0).reset_index()
    users = beh.groupby("bin")["user_id"].nunique().rename("users").reset_index()

    # ---- GMV（仅 paid）----
    paid_ids = orders.loc[orders["status"] == "paid", "order_id"].unique()
    paid_orders = orders[orders["order_id"].isin(paid_ids)][["order_id", "user_id"]]
    oi = (
        order_items[order_items["order_id"].isin(paid_ids)]
        .merge(dim[["item_id", "bin"]], on="item_id", how="inner")
        .merge(paid_orders, on="order_id", how="inner")
    )
    gmv = oi.groupby("bin")["amount"].sum().rename("gmv")
    ocount = oi.groupby("bin")["order_id"].nunique().rename("orders")
    buy_users = oi.groupby("bin")["user_id"].nunique().rename("buy_users")

    item_count = dim.groupby("bin")["item_id"].nunique().rename("item_count")

    table = (
        item_count.reset_index()
        .merge(rates, on="bin", how="left")
        .merge(users, on="bin", how="left")
        .merge(gmv.reset_index(), on="bin", how="left")
        .merge(ocount.reset_index(), on="bin", how="left")
        .merge(buy_users.reset_index(), on="bin", how="left")
    )
    for col in ("pv", "click", "collect", "cart", "buy"):
        if col not in table.columns:
            table[col] = 0
    for col in ("pv", "click", "collect", "cart", "buy", "users", "orders", "buy_users", "item_count"):
        table[col] = pd.to_numeric(table[col], errors="coerce").fillna(0).astype(int)
    table["gmv"] = pd.to_numeric(table["gmv"], errors="coerce").fillna(0.0)
    table["click_rate"] = [safe_div(c, p) for c, p in zip(table["click"], table["pv"])]
    table["cart_rate"] = [safe_div(c, p) for c, p in zip(table["cart"], table["pv"])]
    table["buy_rate"] = [safe_div(b, p) for b, p in zip(table["buy"], table["pv"])]
    table["buy_freq"] = [safe_div(o, u) for o, u in zip(table["orders"], table["buy_users"])]
    table["user_value"] = [safe_div(g, u) for g, u in zip(table["gmv"], table["buy_users"])]

    table = table.sort_values("gmv", ascending=False)

    bins = []
    for r in table.to_dict("records"):
        lo, hi, label = bin_label[int(r["bin"])]
        bins.append({
            "bin_label": label,
            "price_min": round(float(lo), 2),
            "price_max": round(float(hi), 2),
            "item_count": int(r["item_count"]),
            "pv": int(r["pv"]),
            "click": int(r["click"]),
            "cart": int(r["cart"]),
            "buy": int(r["buy"]),
            "click_rate": round(float(r["click_rate"]), 4),
            "cart_rate": round(float(r["cart_rate"]), 4),
            "buy_rate": round(float(r["buy_rate"]), 4),
            "orders": int(r["orders"]),
            "gmv": round(float(r["gmv"]), 2),
            "buy_users": int(r["buy_users"]),
            "buy_freq": round(float(r["buy_freq"]), 4),
            "user_value": round(float(r["user_value"]), 2),
        })

    cross = {
        "price_vs_buy_rate": _corr_bins(bins, "price_min", "buy_rate"),
        "price_vs_buy_freq": _corr_bins(bins, "price_min", "buy_freq"),
        "price_vs_user_value": _corr_bins(bins, "price_min", "user_value"),
    }

    return {
        "definition": (
            f"价格按 items.price 自动分 {cfg.n_bins} 箱（等频，冲突退化等宽）；"
            "费率=区间内行为汇总比；GMV 仅统计 paid；"
            "购买频率=区间购买用户人均订单数；用户价值=区间购买用户人均 GMV。"
        ),
        "config": {"n_bins": cfg.n_bins, "top_n": cfg.top_n},
        "total_price_bins": len(bins),
        "price_bins": bins[:cfg.top_n if cfg.top_n else len(bins)],
        "cross": cross,
    }


def _auto_bin(series: pd.Series, n_bins: int) -> tuple[list, list]:
    """返回 (区间描述, 边界)；等频失败退化等宽。delim"""
    try:
        out, edges = pd.qcut(series, q=n_bins, duplicates="drop", retbins=True)
    except (ValueError, TypeError):
        out, edges = pd.cut(series, bins=n_bins, retbins=True)
    intervals = list(out.cat.categories)
    return ([(_i.left, _i.right, str(_i)) for _i in intervals], list(edges))


def _assign_bin(price: float, edges: list, descriptions: list) -> int:
    """按价格返回箱序号。"""
    last = len(edges) - 2
    for i in range(last + 1):
        lo, hi = edges[i], edges[i + 1]
        if price <= hi:
            return i
    return last


def _corr_bins(bins: list, x_key: str, y_key: str) -> dict:
    """区间级相关性：仅当 >=3 个区间时计算 Pearson 近似。"""
    if len(bins) < 3:
        return {"bins": len(bins), "aligned": 0, "correlation": 0.0}
    xs = [b[x_key] for b in bins]
    ys = [b[y_key] for b in bins]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    sdx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
    sdy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
    corr = safe_div(cov, sdx * sdy, scale=4)
    return {"bins": n, "aligned": 1, "correlation": float(corr)}