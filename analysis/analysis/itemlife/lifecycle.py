"""商品生命周期分析（开发文档第 25 节）。

按时间窗口统计商品的曝光(PV)/点击/加购/购买/GMV 趋势，并结合销量变化与
趋势斜率判定阶段：新品 / 成长 / 爆款 / 成熟 / 衰退。

口径（明确定义）：
- 窗口：以分析日为界、按天粒度滚动取最近 ``n_windows`` 个窗口，
  每窗口跨 ``window_days`` 天（默认 7 天一周）；
- 阶段判定（可配置，自上而下首个命中）：
    1. 新品：商品创建日期距分析日 <= ``new_item_days``（默认 30 天）；
    2. 衰退：最近窗口购买次数下降（最近窗口 vs 前窗口 <= ``decline_ratio``）
      且最近窗口购买次数 > 0；
    3. 成长：近半段购买趋势上升（slope > ``growth_slope``）且当前窗口有购买；
    4. 爆款：最近窗口购买次数 >= ``hot_buy_min`` 且热销保持（近半段均值高）；
    5. 成熟：有购买、趋势平稳（其余有购买的商品）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..base import safe_div


@dataclass(frozen=True)
class ItemLifeConfig:
    """商品生命周期分析配置。"""

    n_windows: int = 4                 # 窗口数（最近 N 个窗口）
    window_days: int = 7               # 每窗口天数（默认按周）
    new_item_days: int = 30            # 新品判定：创建距今 <= N 天
    decline_ratio: float = 0.6         # 最近窗口 vs 前窗口 <= 该比例 -> 衰退
    growth_slope: float = 0.0          # 购买趋势斜率阈值 -> 成长
    hot_buy_min: int = 10              # 最近窗口购买次数 >= 该值 -> 可能爆款


def item_lifecycle_analysis(
    items: pd.DataFrame,
    behaviors: pd.DataFrame,
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    cfg: ItemLifeConfig | None = None,
) -> dict:
    """按商品判定生命周期阶段。

    参数:
        items: items.csv，至少含 item_id / created_at / price / status
        behaviors: user_behaviors.csv，至少含 item_id / behavior_type / event_date
        order_items: order_items.csv，至少含 item_id / amount / order_id
        orders: orders.csv，至少含 order_id / status
        cfg: 商品生命周期配置

    返回:
        dict:
        - definition / config
        - window: 窗口起点列表（date 字符串）
        - distribution: [{stage, count, ratio, total_gmv}]
        - items: list[{"item_id","item_name","price","stage",
                       "buy_trend","slope","total_buy","total_gmv"}]
    """
    cfg = cfg or ItemLifeConfig()

    beh = behaviors[["item_id", "behavior_type", "event_date"]].copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    beh = beh.dropna(subset=["event_date"])
    as_of = beh["event_date"].max()

    # ---- 行为窗口透视（按商品×窗口 的 pv/click/cart/buy 计数）----
    # 手动构造窗口：最近 n_windows 个整窗口
    windows = _build_windows(as_of, cfg.n_windows, cfg.window_days)
    window_min = windows[0]["start"]
    w_beh = beh[beh["event_date"] >= window_min].copy()
    w_beh["window_idx"] = [
        int((d - window_min).days // cfg.window_days) if pd.notna(d) else -1
        for d in w_beh["event_date"]
    ]
    w_beh = w_beh[w_beh["window_idx"] >= 0]

    pivot = w_beh.groupby(["item_id", "window_idx", "behavior_type"]).size().unstack(fill_value=0)
    for bt in ("pv", "click", "cart", "buy"):
        if bt not in pivot.columns:
            pivot[bt] = 0
    pivot = pivot[["pv", "click", "cart", "buy"]]

    # ---- GMV（仅 paid）----
    paid_ids = orders.loc[orders["status"] == "paid", "order_id"].unique()
    oi = order_items[order_items["order_id"].isin(paid_ids)]
    gmv = oi.groupby("item_id")["amount"].sum().rename("total_gmv")

    dim = items[["item_id", "item_name", "price", "status", "created_at"]].copy()
    dim["created_at"] = pd.to_datetime(dim["created_at"], errors="coerce")
    dim["price"] = pd.to_numeric(dim["price"], errors="coerce")

    rows = []
    for iid in dim["item_id"]:
        sub = pivot.loc[iid] if iid in pivot.index else pd.DataFrame(
            columns=["pv", "click", "cart", "buy"]).reindex(range(cfg.n_windows), fill_value=0)
        total_buy = int(sub["buy"].sum())
        total_pv = int(sub["pv"].sum())
        # 趋势：按窗口购买次数线性斜率
        slope = _slope([int(x) for x in sub["buy"].fillna(0)])
        stage = _stage_of(
            slope=slope,
            recent_buy=int(sub["buy"].iloc[-1]) if len(sub) else 0,
            prev_buy=int(sub["buy"].iloc[-2]) if len(sub) > 1 else 0,
            total_buy=total_buy,
            created_at=dim.loc[dim["item_id"] == iid, "created_at"].iloc[0],
            as_of=as_of,
            cfg=cfg,
        )
        rows.append({
            "item_id": iid,
            "item_name": dim.loc[dim["item_id"] == iid, "item_name"].iloc[0],
            "price": round(float(dim.loc[dim["item_id"] == iid, "price"].iloc[0]), 2),
            "stage": stage,
            "buy_trend": [int(x) for x in sub["buy"].fillna(0)],
            "slope": round(float(slope), 4),
            "total_pv": total_pv,
            "total_buy": total_buy,
            "total_gmv": round(float(gmv.get(iid, 0.0)), 2),
        })

    out_df = pd.DataFrame(rows)
    distribution = [
        {
            "stage": s,
            "count": int((out_df["stage"] == s).sum()),
            "ratio": safe_div(int((out_df["stage"] == s).sum()), len(out_df)),
            "total_gmv": round(float(out_df.loc[out_df["stage"] == s, "total_gmv"].sum()), 2),
        }
        for s in ("新品", "成长", "爆款", "成熟", "衰退", "无购买")
    ]
    out_df = out_df.sort_values("total_gmv", ascending=False)

    return {
        "definition": (
            f"按最近 {cfg.n_windows} 个窗口（每 {cfg.window_days} 天）统计购买趋势与 GMV 判定阶段："
            f"新品=创建距今≤{cfg.new_item_days}天；衰退=最近窗口购买≤前窗口×{cfg.decline_ratio}；"
            f"成长=购买斜率>{cfg.growth_slope}；爆款=最近窗口购买≥{cfg.hot_buy_min}；其余有购买=成熟。"
        ),
        "config": {
            "n_windows": cfg.n_windows,
            "window_days": cfg.window_days,
            "new_item_days": cfg.new_item_days,
            "decline_ratio": cfg.decline_ratio,
            "growth_slope": cfg.growth_slope,
            "hot_buy_min": cfg.hot_buy_min,
        },
        "window_start_dates": [w["start"].strftime("%Y-%m-%d") for w in windows],
        "total_items": int(len(out_df)),
        "distribution": distribution,
        "items": out_df.to_dict("records"),
    }


def _build_windows(as_of: pd.Timestamp, n_windows: int, window_days: int) -> list[dict]:
    """从分析日起向前构造 n_windows 个连续窗口。"""
    as_of = as_of.normalize()
    end = as_of + pd.Timedelta(days=1)
    start = end - pd.Timedelta(days=n_windows * window_days)
    windows = []
    for i in range(n_windows):
        s = start + pd.Timedelta(days=i * window_days)
        e = start + pd.Timedelta(days=(i + 1) * window_days)
        windows.append({"start": s, "end": min(e, end)})
    return windows


def _slope(y: list[float]) -> float:
    """最小二乘趋势斜率（窗口序号 → 购买次数）。"""
    n = len(y)
    if n < 2 or sum(y) == 0:
        return 0.0
    x = np.arange(n, dtype=float)
    if np.std(x) == 0:
        return 0.0
    return float(np.polyfit(x, np.asarray(y, dtype=float), 1)[0])


def _stage_of(slope: float, recent_buy: int, prev_buy: int, total_buy: int,
              created_at, as_of, cfg: ItemLifeConfig) -> str:
    if total_buy == 0:
        return "无购买"
    if created_at is not None and pd.notna(created_at):
        days = (as_of - created_at).days
        if days <= cfg.new_item_days:
            return "新品"
    if prev_buy > 0 and recent_buy <= prev_buy * cfg.decline_ratio:
        return "衰退"
    if recent_buy > 0 and slope > cfg.growth_slope:
        return "成长"
    if recent_buy >= cfg.hot_buy_min:
        return "爆款"
    return "成熟"