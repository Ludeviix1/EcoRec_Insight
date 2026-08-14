"""维度数据仓库：读取 data/processed 下 users / items / categories 清洗 CSV。

processed CSV 由 run_etl.py 产出，与 MySQL 落库口径一致；进程内缓存后按需过滤分页。
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from ..core.exceptions import NotFoundError
from .base import PROCESSED_DIR

_USER_DTYPE = {"user_id": str}
_ITEM_DTYPE = {"item_id": str, "category_id": str, "brand": str}
_CATEGORY_DTYPE = {"category_id": str, "parent_id": str}


@lru_cache(maxsize=1)
def users_df() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / "users.csv", dtype=_USER_DTYPE)
    df["register_time"] = df["register_time"].astype(str)
    return df


@lru_cache(maxsize=1)
def items_df() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "items.csv", dtype=_ITEM_DTYPE)


@lru_cache(maxsize=1)
def categories_df() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "categories.csv", dtype=_CATEGORY_DTYPE)


@lru_cache(maxsize=1)
def _user_index() -> dict[str, dict]:
    return {r["user_id"]: r for r in users_df().to_dict("records")}


@lru_cache(maxsize=1)
def _item_index() -> dict[str, dict]:
    return {r["item_id"]: r for r in items_df().to_dict("records")}


@lru_cache(maxsize=1)
def _category_map() -> dict[str, str]:
    df = categories_df()
    return dict(zip(df["category_id"], df["category_name"]))


def category_name(category_id: str) -> str:
    return str(_category_map().get(str(category_id), ""))


def list_users(keyword: str | None = None, limit: int = 20, offset: int = 0) -> dict:
    df = users_df()
    if keyword:
        kw = keyword.strip()
        mask = df["user_id"].str.contains(kw, case=False, na=False)
        if "city" in df.columns:
            mask = mask | df["city"].astype(str).str.contains(kw, case=False, na=False)
        df = df[mask]
    total = int(len(df))
    page = df.iloc[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": page[["user_id", "age", "gender", "city", "register_time"]].to_dict("records"),
    }


def get_user(user_id: str) -> dict:
    idx = _user_index()
    row = idx.get(str(user_id))
    if row is None:
        raise NotFoundError(message=f"用户不存在: {user_id}")
    return dict(row)


_SORTABLE = ("brand", "price", "stock")


@lru_cache(maxsize=1024)
def _pinyin_key(text: str) -> str:
    """品牌转拼音首字母（'华为' -> 'hw'）；非中文原样保留并统一小写，保证与中文混排可比。"""
    from pypinyin import Style, lazy_pinyin

    return "".join(lazy_pinyin(text, style=Style.FIRST_LETTER)).lower()


def list_items(
    keyword: str | None = None,
    category_id: str | None = None,
    brand: str | None = None,
    status: int | None = None,
    sort_by: str | None = None,
    order: str = "asc",
    on_shelf_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    df = items_df()
    if keyword:
        kw = keyword.strip()
        mask = df["item_id"].astype(str).str.contains(kw, case=False, na=False)
        if "item_name" in df.columns:
            mask = mask | df["item_name"].astype(str).str.contains(kw, case=False, na=False)
        df = df[mask]
    if category_id:
        df = df[df["category_id"].astype(str) == str(category_id)]
    if brand:
        df = df[df["brand"].astype(str).str.contains(brand.strip(), case=False, na=False)]
    if status is not None:
        df = df[df["status"].astype(int) == int(status)]
    if on_shelf_only:
        df = df[df["status"].astype(int) == 1]
    if sort_by in _SORTABLE:
        ascending = str(order).lower() != "desc"
        if sort_by == "brand":
            key = df["brand"].map(lambda v: _pinyin_key(v) if isinstance(v, str) else v)
            df = df.assign(_sort_key=key)
            df = df.sort_values("_sort_key", ascending=ascending, kind="stable", na_position="last").drop(columns="_sort_key")
        else:
            df = df.sort_values(sort_by, ascending=ascending, kind="stable", na_position="last")
    total = int(len(df))
    page = df.iloc[offset : offset + limit]
    records = page.to_dict("records")
    for r in records:
        r["category_name"] = category_name(r.get("category_id"))
    return {"total": total, "limit": limit, "offset": offset, "items": records}


def get_item(item_id: str) -> dict:
    idx = _item_index()
    row = idx.get(str(item_id))
    if row is None:
        raise NotFoundError(message=f"商品不存在: {item_id}")
    row = dict(row)
    row["category_name"] = category_name(row.get("category_id"))
    return row