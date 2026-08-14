"""商品路由：/api/items

列表 / 详情 / 排行 / 统计（开发文档第 38 节 + 39.4 节）。
"""

from fastapi import APIRouter, Query

from ..schemas.common import ApiResponse, ok
from ..services import item_service

router = APIRouter(tags=["items"])


@router.get("/ranking", response_model=ApiResponse[dict], summary="商品/分类/品牌排行")
def ranking(top_n: int = Query(10, ge=1, le=100)) -> ApiResponse[dict]:
    return ok(item_service.get_rankings(top_n=top_n))


@router.get("", response_model=ApiResponse[dict], summary="商品列表（分页/关键字/分类）")
def list_items(
    keyword: str | None = Query(None, description="搜索 item_id / item_name"),
    category_id: str | None = Query(None, description="分类 ID"),
    brand: str | None = Query(None, description="品牌（模糊匹配）"),
    status: int | None = Query(None, ge=0, le=1, description="状态：1 上架 / 0 下架"),
    sort_by: str | None = Query(None, pattern="^(brand|price|stock)$", description="排序字段：brand/price/stock"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="排序方向：asc/desc"),
    on_shelf_only: bool = Query(False, description="只看上架"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ApiResponse[dict]:
    return ok(item_service.list_items(
        keyword=keyword, category_id=category_id, brand=brand, status=status,
        sort_by=sort_by, order=order, on_shelf_only=on_shelf_only, limit=limit, offset=offset,
    ))


@router.get("/{item_id}/statistics", response_model=ApiResponse[dict], summary="商品画像统计")
def item_statistics(item_id: str) -> ApiResponse[dict]:
    return ok(item_service.get_item_statistics(item_id))


@router.get("/{item_id}", response_model=ApiResponse[dict], summary="商品详情 + 统计")
def get_item(item_id: str) -> ApiResponse[dict]:
    return ok(item_service.get_item(item_id))