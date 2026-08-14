"""分析全量入口（Phase 5 / 6 / 7）。

读取 data/processed 六张清洗 CSV，依次计算：
Phase 5：用户规模 / DAU·WAU·MAU / 行为分析 / 活跃时间 / GMV / 商品排行 /
分类排行 / 品牌排行 / 漏斗；
Phase 6：留存 / Cohort / RFM；
Phase 7：生命周期 / 购买路径 / 商品生命周期 / 价格 / 渠道 / 设备 /
关联规则 / 用户分群 / 用户画像 / 商品画像 / 业务发现。
每个结果写成 data/analysis/<name>.json（结构化数据，
供后续 FastAPI 直接复用，开发文档第 49.3/49.4/49.5 节）。
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from .association import association_analysis
from .base import load_processed, write_json
from .channel import channel_analysis, device_analysis
from .cohort import cohort_analysis
from .config import AnalysisConfig, load_analysis_config
from .findings import build_findings
from .funnel import conversion_funnel
from .gmv import gmv_analysis
from .item import brand_ranking, category_ranking, item_ranking
from .itemlife import item_lifecycle_analysis
from .lifecycle import lifecycle_analysis
from .path import purchase_path_analysis
from .price import price_analysis
from .profile import item_profile, user_profile
from .retention import retention_analysis
from .rfm import rfm_analysis
from .segmentation import user_segmentation
from .user import active_time, behavior_analysis, dau_wau_mau, user_scale

logger = logging.getLogger("analysis.base")


def run_analysis(cfg: AnalysisConfig | None = None, *, log: bool = True) -> dict:
    """执行全部分析，返回结果 dict（同时已落盘 JSON）。"""
    cfg = cfg or load_analysis_config()
    if log:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    t0 = time.perf_counter()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    users = load_processed(cfg.processed_dir, "users")
    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")

    logger.info("加载 processed 完成 | users=%d items=%d behaviors=%d orders=%d order_items=%d",
                len(users), len(items), len(behaviors), len(orders), len(order_items))

    top_n = cfg.top_n
    results: dict[str, dict] = {
        "user_scale": user_scale(users, behaviors),
        "dau_wau_mau": dau_wau_mau(behaviors),
        "behavior": behavior_analysis(behaviors),
        "active_time": active_time(behaviors),
        "gmv": gmv_analysis(orders, behaviors),
        "item_ranking": item_ranking(items, behaviors, order_items, orders, top_n=top_n),
        "category_ranking": category_ranking(items, behaviors, order_items, orders, top_n=top_n),
        "brand_ranking": brand_ranking(items, behaviors, order_items, orders, top_n=top_n),
        "funnel": conversion_funnel(behaviors),
        "retention": retention_analysis(behaviors),
        "cohort": cohort_analysis(behaviors),
        "rfm": rfm_analysis(orders),
        # ---- Phase 7 深度业务分析 ----
        "lifecycle": lifecycle_analysis(users, behaviors, orders),
        "purchase_path": purchase_path_analysis(behaviors),
        "item_lifecycle": item_lifecycle_analysis(items, behaviors, order_items, orders),
        "price": price_analysis(items, behaviors, order_items, orders),
        "channel": channel_analysis(users, behaviors, orders),
        "device": device_analysis(users, behaviors, orders),
        "association": association_analysis(order_items, orders, items),
        "user_segments": user_segmentation(behaviors, orders),
        "user_profile": user_profile(users, behaviors, orders, order_items, items),
        "item_profile": item_profile(items, behaviors, order_items, orders),
    }
    # 业务发现基于以上结果（不含自身）
    results["findings"] = build_findings(results)

    for name, data in results.items():
        write_json(cfg.output_dir / f"{name}.json", data)
        logger.info("写入 %s.json (%s 条)", name, _size_hint(data))

    # ---- 运行记录 ----
    meta = {
        "analysis_version": cfg.analysis_version,
        "dataset_version": _dataset_version(cfg),
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "top_n": top_n,
        "processed_dir": str(cfg.processed_dir),
        "output_dir": str(cfg.output_dir),
        "results": list(results.keys()),
    }
    write_json(cfg.output_meta_path, meta)
    logger.info("基础分析完成 in %ss | 输出: %s", meta["elapsed_seconds"], cfg.output_dir)
    return results


def _size_hint(data: dict) -> str:
    if isinstance(data, dict) and "items" in data:
        return str(data.get("total", len(data["items"])))
    if isinstance(data, dict) and "cohorts" in data:
        return str(data.get("total_cohorts", len(data["cohorts"])))
    if isinstance(data, dict) and "users" in data:
        return str(data.get("total_buying_users", len(data["users"])))
    if isinstance(data, dict) and "profiles" in data:
        return str(data.get("total_users", len(data["profiles"])))
    if isinstance(data, dict) and "top_paths" in data:
        return str(data.get("distinct_paths", len(data["top_paths"])))
    if isinstance(data, dict) and "clusters" in data:
        return str(len(data["clusters"]))
    if isinstance(data, dict) and "rules" in data:
        return str(data.get("rules_count", len(data["rules"])))
    if isinstance(data, dict) and "item_rules" in data:
        return f"{data.get('item_rules_count', 0)}+{data.get('category_rules_count', 0)}"
    if isinstance(data, dict) and "domains" in data:
        return str(data.get("total_domains", len(data["domains"])))
    if isinstance(data, dict) and "distribution" in data:
        return str(len(data["distribution"]))
    if isinstance(data, dict) and "devices" in data:
        return str(len(data["devices"]))
    if isinstance(data, dict) and "channels" in data:
        return str(len(data["channels"]))
    return str(len(data)) if isinstance(data, list) else "-"


def _dataset_version(cfg: AnalysisConfig) -> str:
    """从 etl_meta.json 读取 dataset_version，缺失则返回 'unknown'。"""
    p = cfg.interim_dir / "etl_meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("dataset_version", "unknown")
        except Exception:
            return "unknown"
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="分析入口: 用户/DAU/GMV/排行/漏斗/留存/Cohort/RFM/生命周期/路径/商品生命周期/价格/渠道/设备/关联规则/分群/画像/发现",
    )
    parser.add_argument("--processed-dir", type=str, default=None, help="清洗数据目录（默认 data/processed）")
    parser.add_argument("--interim-dir", type=str, default=None, help="中间产物目录（默认 data/interim）")
    parser.add_argument("--output-dir", type=str, default=None, help="分析结果输出目录（默认 data/analysis）")
    parser.add_argument("--analysis-version", type=str, default=None, help="分析版本（默认 1.0）")
    parser.add_argument("--top-n", type=int, default=None, help="排行 TOP N（默认 10）")

    args = parser.parse_args(argv)
    cfg = load_analysis_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
        analysis_version=args.analysis_version,
        top_n=args.top_n,
    )
    run_analysis(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
