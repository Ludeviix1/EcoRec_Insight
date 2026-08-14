"""商品服务：列表 / 详情 / 排行 / 统计。"""

from __future__ import annotations

from ..repositories import analysis_repo, catalog_repo


def list_items(
    keyword: str | None = None,
    category_id: str | None = None,
    on_shelf_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    return catalog_repo.list_items(
        keyword=keyword, category_id=category_id, on_shelf_only=on_shelf_only, limit=limit, offset=offset
    )


def get_item(item_id: str) -> dict:
    """商品基础信息 + 画像统计。"""
    row = catalog_repo.get_item(item_id)
    try:
        stat = analysis_repo.item_profile(item_id)
    except Exception:
        stat = {}
    row["statistics"] = {
        "behavior": stat.get("behavior"),
        "sales": stat.get("sales"),
        "lifecycle_stage": stat.get("lifecycle_stage"),
        "price_band": stat.get("price_band"),
        "heat_score": stat.get("heat_score"),
    }
    return row


def get_item_statistics(item_id: str) -> dict:
    return analysis_repo.item_profile(item_id)


def get_rankings(top_n: int = 10) -> dict:
    items = analysis_repo.get_item("item-ranking")
    categories = analysis_repo.get_item("category-ranking")
    brands = analysis_repo.get_item("brand-ranking")
    return {
        "top_n": top_n,
        "items": (items.get("items") or [])[:top_n],
        "categories": (categories.get("categories") or [])[:top_n],
        "brands": (brands.get("brands") or [])[:top_n],
    }