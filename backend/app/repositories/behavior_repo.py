"""事实数据仓库：读取 data/processed 下 user_behaviors / orders / order_items 清洗 CSV。

行为/订单量较大（数十万级），进程内缓存整表后按 user_id 过滤，避免重复读盘。
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from ..core.exceptions import NotFoundError
from .base import PROCESSED_DIR

_UID_DTYPE = {"user_id": str}


@lru_cache(maxsize=1)
def behaviors_df() -> pd.DataFrame:
    df = pd.read_csv(
        PROCESSED_DIR / "user_behaviors.csv",
        dtype={"user_id": str, "item_id": str, "behavior_type": str, "channel": str, "device_type": str},
    )
    df["event_date"] = df["event_date"].astype(str)
    df["event_time"] = df["event_time"].astype(str)
    return df


@lru_cache(maxsize=1)
def orders_df() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / "orders.csv", dtype={"user_id": str})
    df["order_time"] = df["order_time"].astype(str)
    return df


@lru_cache(maxsize=1)
def order_items_df() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "order_items.csv", dtype={"order_id": str, "item_id": str})


def user_exists(user_id: str) -> bool:
    """校验用户是否存在（供行为/订单类接口前置检查）。"""
    from .catalog_repo import get_user

    try:
        get_user(user_id)
        return True
    except NotFoundError:
        return False


def list_user_behaviors(user_id: str, limit: int = 100) -> dict:
    if not user_exists(user_id):
        raise NotFoundError(message=f"用户不存在: {user_id}")
    df = behaviors_df()
    sub = df[df["user_id"] == str(user_id)]
    total = int(len(sub))
    order = ["event_time", "event_date", "event_hour", "behavior_type", "item_id", "device_type", "channel"]
    page = sub.sort_values("event_time", ascending=False).head(limit)
    cols = [c for c in order if c in page.columns]
    return {"user_id": str(user_id), "total": total, "limit": limit, "items": page[cols].to_dict("records")}


def list_user_orders(user_id: str) -> dict:
    if not user_exists(user_id):
        raise NotFoundError(message=f"用户不存在: {user_id}")
    odf = orders_df()
    sub = odf[odf["user_id"] == str(user_id)].sort_values("order_time", ascending=False)
    oi = order_items_df()
    items = []
    for _, o in sub.iterrows():
        items.append(
            {
                "order_id": o["order_id"],
                "order_time": o["order_time"],
                "total_amount": float(o["total_amount"]),
                "status": o["status"],
                "payment_method": o["payment_method"],
                "order_items": oi[oi["order_id"] == o["order_id"]].to_dict("records"),
            }
        )
    paid = sub[sub["status"] == "paid"]
    return {
        "user_id": str(user_id),
        "total_orders": int(len(sub)),
        "paid_orders": int(len(paid)),
        "paid_gmv": round(float(paid["total_amount"].sum()), 2),
        "items": items,
    }