"""推荐仓库：加载推荐模型并服务（离线训练 → 模型加载 → API 服务）。

- popular / content / hybrid：加载 run_recommendation / run_content / run_hybrid 保存的
  joblib 模型（含已过滤上下文）；
- itemcf / usercf：Phase 12/14 仅离线评估未持久化模型，这里在进程内**一次性**构建并缓存，
  属于"离线训练 → 加载"而非每次请求重训（开发文档第 46 节）。

所有模型进程级缓存，首次请求构建后常驻内存。
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache

import joblib
import pandas as pd

from ..core.exceptions import NotFoundError, ValidationError
from .base import PROCESSED_DIR, RECOMMENDATION_DIR, RECOMMEND_ALGORITHMS

logger = logging.getLogger("api.recommendation_repo")

_MODELS: dict[str, object] = {}
_LOCK = threading.Lock()


def _recommend_cfg():
    from analysis.recommendation.config import load_recommend_config

    return load_recommend_config()


@lru_cache(maxsize=1)
def _processed_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from analysis.feature_engineering.base import load_processed

    return (
        load_processed(PROCESSED_DIR, "items"),
        load_processed(PROCESSED_DIR, "user_behaviors"),
        load_processed(PROCESSED_DIR, "orders"),
        load_processed(PROCESSED_DIR, "order_items"),
    )


def _build_online_recommender(name: str) -> object:
    """进程内一次性构建 itemcf / usercf 推荐器（离线训练 + 缓存）。"""
    from analysis.recommendation.itemcf import ItemCFRecommender
    from analysis.recommendation.usercf import UserCFRecommender

    items, behaviors, orders, order_items = _processed_tables()
    cls = ItemCFRecommender if name == "itemcf" else UserCFRecommender
    t0 = __import__("time").perf_counter()
    model = cls(_recommend_cfg()).fit(behaviors, items, orders, order_items)
    logger.info("%s 在线模型构建完成 in %.1fs", name, __import__("time").perf_counter() - t0)
    return model


def _load_joblib(name: str) -> object:
    path = {
        "popular": RECOMMENDATION_DIR / "popular_model.joblib",
        "content": RECOMMENDATION_DIR / "content_model.joblib",
        "hybrid": RECOMMENDATION_DIR / "hybrid_model.joblib",
    }[name]
    if not path.exists():
        raise NotFoundError(
            message=f"{name} 模型不存在，请先运行对应脚本（scripts/run_recommendation.py / run_content.py / run_hybrid.py）"
        )
    model = joblib.load(path)
    logger.info("%s 模型加载 %s", name, path.name)
    return model


def get_recommender(name: str) -> object:
    """返回推荐器实例（进程内缓存）。"""
    name = str(name).strip().lower()
    if name not in RECOMMEND_ALGORITHMS:
        raise ValidationError(message=f"未知推荐算法: {name}，可选 {list(RECOMMEND_ALGORITHMS)}")
    if name in _MODELS:
        return _MODELS[name]
    with _LOCK:
        if name in _MODELS:
            return _MODELS[name]
        if name in ("popular", "content", "hybrid"):
            model = _load_joblib(name)
        else:
            model = _build_online_recommender(name)
        _MODELS[name] = model
        return model