"""推荐系统全量入口（Phase 11，开发文档第 49.9 节）。

流程：
    data/processed 读取
        ↓
    PopularRecommender.fit（行为加权 + 时间衰减 + min-max 标准化）
        ↓
    data/recommendation/: popular_model.joblib + popular_items.csv
    + popular_recommendations.csv（全体活跃用户 Top-K）+ recommendation_meta.json
"""

from __future__ import annotations

import argparse
import json
import logging
import time

import joblib
import pandas as pd

from analysis.feature_engineering.base import load_processed

from .config import RecommendConfig, load_recommend_config
from .content import ContentRecommender
from .hybrid import HybridRecommender
from .popular import PopularRecommender

logger = logging.getLogger("analysis.recommendation")


def _dataset_version(cfg: RecommendConfig) -> str:
    p = cfg.interim_dir / "etl_meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("dataset_version", "unknown")
        except Exception:
            return "unknown"
    return "unknown"


def build_popular(cfg: RecommendConfig | None = None, *, log: bool = True) -> dict:
    """训练并保存 Popular 模型与推荐结果，返回运行记录 dict。"""
    cfg = cfg or load_recommend_config()
    if log:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    t0 = time.perf_counter()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")
    logger.info("加载 processed 完成 | items=%d behaviors=%d orders=%d",
                len(items), len(behaviors), len(orders))

    model = PopularRecommender(cfg).fit(behaviors, items, orders, order_items)
    joblib.dump(model, cfg.model_path)
    logger.info("模型保存 %s", cfg.model_path.name)

    # 全量热门商品表
    items_out = model.score_table.reset_index()
    items_out = items_out.rename(columns={"index": "item_id"})
    if "item_id" not in items_out.columns:
        items_out = items_out.rename(columns={items_out.columns[0]: "item_id"})
    items_path = cfg.output_dir / "popular_items.csv"
    items_out.to_csv(items_path, index=False, encoding="utf-8-sig")

    # 全体活跃用户推荐 Top-K
    active_users = behaviors["user_id"].astype(str).unique()
    recs = []
    for uid in active_users:
        for r in model.recommend(uid, top_k=cfg.top_k):
            recs.append({"user_id": uid, **r})
    recs_df = pd.DataFrame(recs)
    recs_path = cfg.output_dir / "popular_recommendations.csv"
    recs_df.to_csv(recs_path, index=False, encoding="utf-8-sig")
    logger.info("推荐结果写入 %s (%d 行)", recs_path.name, len(recs_df))

    behavior_comp = {}
    for bt in ("pv", "click", "collect", "cart", "buy"):
        behavior_comp[bt] = {
            "weight": cfg.behavior_weights.get(bt, 0.0),
            "normalized": "max-normalization [0,1]",
        }

    meta = {
        "recommend_version": cfg.recommend_version,
        "dataset_version": _dataset_version(cfg),
        "algorithm": "popular",
        "task": "popular_baseline",
        "score_formula": (
            "score = w_pv*pv_score + w_click*click_score + w_collect*collect_score "
            "+ w_cart*cart_score + w_buy*buy_score（各分量 max-normalization 到 [0,1] + 时间衰减，"
            "最终热度分 min-max 到 [0,1]）"
        ),
        "time_decay": {
            "rule": f"decay = 0.5 ** (days_ago / {cfg.half_life_days})；days_ago 相对参考日",
            "half_life_days": cfg.half_life_days,
            "ref_date": str(model.ref_date.date()),
        },
        "behavior_components": behavior_comp,
        "filtering": {
            "purchased": cfg.filter_purchased,
            "off_shelf": cfg.filter_off_shelf,
            "dedup": True,
        },
        "cold_start": "新用户/少行为用户命中频率: 全局热门 Top-K（Popular 天然支持）",
        "stats": {
            "n_items_scored": int(len(model.score_table)),
            "n_users_recommended": int(len(recs_df["user_id"].unique())) if len(recs_df) else 0,
            "n_recommendations": int(len(recs_df)),
            "top_item": str(model.score_table.index[0]) if len(model.score_table) else None,
            "top_item_score": round(float(model.score_table["score"].iloc[0]), 4) if len(model.score_table) else None,
        },
        "config": {
            "behavior_weights": cfg.behavior_weights,
            "half_life_days": cfg.half_life_days,
            "as_of_date": cfg.as_of_date,
            "top_k": cfg.top_k,
        },
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "model": str(cfg.model_path),
        "items": str(items_path),
        "recommendations": str(recs_path),
    }
    cfg.meta_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Popular 构建完成 in %ss | 输出: %s", meta["elapsed_seconds"], cfg.output_dir)
    return meta


def build_content(cfg: RecommendConfig | None = None, *, log: bool = True) -> dict:
    """训练并保存 Content-Based 模型与推荐结果，返回运行记录 dict。"""
    cfg = cfg or load_recommend_config()
    if log:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    t0 = time.perf_counter()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")
    logger.info("加载 processed 完成 | items=%d behaviors=%d",
                len(items), len(behaviors))

    model = ContentRecommender(cfg).fit(behaviors, items, orders, order_items)
    joblib.dump(model, cfg.content_model_path)
    logger.info("模型保存 %s", cfg.content_model_path.name)

    active_users = behaviors["user_id"].astype(str).unique()
    recs = []
    for uid in active_users:
        for r in model.recommend(uid, top_k=cfg.top_k):
            recs.append({"user_id": uid, **r})
    recs_df = pd.DataFrame(recs)
    recs_path = cfg.output_dir / "content_recommendations.csv"
    recs_df.to_csv(recs_path, index=False, encoding="utf-8-sig")
    logger.info("推荐结果写入 %s (%d 行)", recs_path.name, len(recs_df))

    meta = {
        "recommend_version": cfg.recommend_version,
        "dataset_version": _dataset_version(cfg),
        "algorithm": "content",
        "task": "content_based",
        "features": ["category(one-hot)", "brand(one-hot)", "price_range(qcut 分箱)",
                     "item tags(item_name TF-IDF, 去品牌 token)"],
        "similarity": "cosine similarity",
        "flow": "用户历史商品(种子，行为权重×时间衰减) → 内容相似商品 → 分数累加 → 过滤 → Top-K",
        "filtering": {
            "purchased": cfg.filter_purchased,
            "off_shelf": cfg.filter_off_shelf,
            "dedup": True,
        },
        "cold_start": "新用户→全局热门兜底；新商品→内容特征天然可召回（不需行为），与开发文档 35.6 一致",
        "config": {
            "behavior_weights": cfg.behavior_weights,
            "half_life_days": cfg.half_life_days,
            "n_price_bins": cfg.n_price_bins,
            "sim_top": cfg.sim_top,
            "top_k": cfg.top_k,
        },
        "stats": {
            "n_items_embedded": int(len(model._item_index)) if model._item_index is not None else 0,
            "n_users_recommended": int(len(recs_df["user_id"].unique())) if len(recs_df) else 0,
            "n_recommendations": int(len(recs_df)),
            "ref_date": str(model.ref_date.date()) if getattr(model, "ref_date", None) is not None else None,
        },
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "model": str(cfg.content_model_path),
        "recommendations": str(recs_path),
    }
    cfg.meta_path.parent.mkdir(parents=True, exist_ok=True)
    (cfg.output_dir / "content_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Content 构建完成 in %ss | 输出: %s", meta["elapsed_seconds"], cfg.output_dir)
    return meta


def build_hybrid(cfg: RecommendConfig | None = None, *, log: bool = True) -> dict:
    """训练并保存 Hybrid 模型与推荐结果，返回运行记录 dict。"""
    cfg = cfg or load_recommend_config()
    if log:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    t0 = time.perf_counter()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")
    logger.info("加载 processed 完成 | items=%d behaviors=%d",
                len(items), len(behaviors))

    model = HybridRecommender(cfg).fit(behaviors, items, orders, order_items)
    joblib.dump(model, cfg.hybrid_model_path)
    logger.info("模型保存 %s", cfg.hybrid_model_path.name)

    active_users = behaviors["user_id"].astype(str).unique()
    recs = []
    for uid in active_users:
        for r in model.recommend(uid, top_k=cfg.top_k):
            recs.append({"user_id": uid, **r})
    recs_df = pd.DataFrame(recs)
    recs_path = cfg.output_dir / "hybrid_recommendations.csv"
    recs_df.to_csv(recs_path, index=False, encoding="utf-8-sig")
    logger.info("推荐结果写入 %s (%d 行)", recs_path.name, len(recs_df))

    meta = {
        "recommend_version": cfg.recommend_version,
        "dataset_version": _dataset_version(cfg),
        "algorithm": "hybrid",
        "task": "hybrid",
        "formula": "HybridScore = w1*ItemCF + w2*UserCF + w3*Popular + w4*Content",
        "fusion": "各分量候选分数先归一化到 [0,1] 再按权重线性融合（开发文档 35.5 节）",
        "hybrid_weights": cfg.hybrid_weights,
        "components": {
            "itemcf": {"desc": "item-item 余弦（用户-商品矩阵权重 pv=1..buy=5）"},
            "usercf": {"desc": "user-user 余弦（Top-N 相似用户加权）", "n_neighbors": cfg.n_neighbors},
            "popular": {"desc": "行为加权+时间衰减全局热门"},
            "content": {"desc": "分类/品牌/价格档/标签 余弦相似"},
        },
        "filtering": {"purchased": cfg.filter_purchased, "off_shelf": cfg.filter_off_shelf, "dedup": True},
        "cold_start": "新用户→各分量回退全局热门后融合（开发文档 35.6）",
        "config": {
            "behavior_weights": cfg.behavior_weights,
            "half_life_days": cfg.half_life_days,
            "n_price_bins": cfg.n_price_bins,
            "sim_top": cfg.sim_top,
            "n_neighbors": cfg.n_neighbors,
            "top_k": cfg.top_k,
        },
        "stats": {
            "n_users_recommended": int(len(recs_df["user_id"].unique())) if len(recs_df) else 0,
            "n_recommendations": int(len(recs_df)),
        },
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "model": str(cfg.hybrid_model_path),
        "recommendations": str(recs_path),
    }
    cfg.meta_path.parent.mkdir(parents=True, exist_ok=True)
    (cfg.output_dir / "hybrid_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Hybrid 构建完成 in %ss | 输出: %s", meta["elapsed_seconds"], cfg.output_dir)
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Popular Baseline: 行为加权+时间衰减 -> data/recommendation",
    )
    parser.add_argument("--processed-dir", type=str, default=None, help="清洗数据目录（默认 data/processed）")
    parser.add_argument("--interim-dir", type=str, default=None, help="中间产物目录（默认 data/interim）")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录（默认 data/recommendation）")
    parser.add_argument("--behavior-weights", type=str, default=None,
                        help='行为权重，JSON 或 "pv:1,click:2,collect:3,cart:4,buy:5"')
    parser.add_argument("--half-life-days", type=float, default=None, help="时间衰减半衰期（天数，默认 7）")
    parser.add_argument("--as-of-date", type=str, default=None, help="热度参考日（默认=行为数据最大日期）")
    parser.add_argument("--top-k", type=int, default=None, help="每个用户推荐条数（默认 10）")

    args = parser.parse_args(argv)
    cfg = load_recommend_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
        behavior_weights=args.behavior_weights,
        half_life_days=args.half_life_days,
        as_of_date=args.as_of_date,
        top_k=args.top_k,
    )
    build_popular(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())