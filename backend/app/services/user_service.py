"""用户服务：列表 / 详情 / 画像 / 行为 / 订单 / 个人维度推荐与预测。"""

from __future__ import annotations

from ..repositories import analysis_repo, behavior_repo, catalog_repo, model_repo, recommendation_repo
from .recommendation_service import recommend as recommend_for_user


def list_users(keyword: str | None = None, limit: int = 20, offset: int = 0) -> dict:
    return catalog_repo.list_users(keyword=keyword, limit=limit, offset=offset)


def get_user(user_id: str) -> dict:
    """基础信息 + 画像摘要（行为 / 购买 / 生命周期 / RFM）。"""
    row = catalog_repo.get_user(user_id)
    try:
        p = analysis_repo.user_profile(user_id)
    except Exception:
        p = {}
    return {
        **row,
        "summary": {
            "behavior": p.get("behavior"),
            "purchase": p.get("purchase"),
            "spending_power": p.get("spending_power"),
            "lifecycle_stage": p.get("lifecycle_stage"),
            "rfm": p.get("rfm"),
        },
    }


def get_user_profile(user_id: str) -> dict:
    """完整用户画像（base/behavior/purchase/偏好/占用）+ 购买/流失预测。"""
    profile = analysis_repo.user_profile(user_id)
    profile["predictions"] = {
        "purchase": model_repo.user_purchase_prediction(user_id),
        "churn": model_repo.user_churn_prediction(user_id),
    }
    return profile


def get_user_behaviors(user_id: str, limit: int = 100) -> dict:
    return behavior_repo.list_user_behaviors(user_id, limit=limit)


def get_user_orders(user_id: str) -> dict:
    result = behavior_repo.list_user_orders(user_id)
    # 订单明细补齐商品名
    item_names = _item_name_map()
    for o in result.get("items", []):
        for oi in o.get("order_items", []):
            oi["item_name"] = item_names.get(str(oi.get("item_id")), "")
    return result


def get_user_recommendations(user_id: str, algorithm: str = "popular", top_k: int = 10) -> dict:
    return recommend_for_user(user_id, algorithm=algorithm, top_k=top_k)


def validate_user(user_id: str) -> None:
    catalog_repo.get_user(user_id)


def _item_name_map() -> dict:
    df = catalog_repo.items_df()
    return dict(zip(df["item_id"].astype(str), df["item_name"].astype(str)))