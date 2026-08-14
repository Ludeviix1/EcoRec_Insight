"""特征工程全量入口（Phase 8，开发文档第 49.6 节）。

流程：
    data/processed（六张清洗 CSV）
        ↓
    用户特征 / 商品特征 / 用户-商品交互特征
        ↓
    data/features/ 三张特征 CSV +
    feature_dictionary.json（数据字典）+
    feature_meta.json（feature_version / feature_time_range / 行数 / 版本血缘）

防泄漏：所有聚合只使用观察窗口内数据，不读取未来标签；纯函数 + 固定窗口 => 可复现。
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from .base import load_processed, observation_window, write_csv
from .config import FeatureConfig, load_feature_config
from .dictionary import feature_dictionary
from .item_features import build_item_features
from .user_features import build_user_features
from .user_item_features import build_user_item_features

logger = logging.getLogger("analysis.feature_engineering")


def run_feature_engineering(cfg: FeatureConfig | None = None, *, log: bool = True) -> dict:
    """执行特征工程，返回运行记录 dict（meta 已落盘 data/features/feature_meta.json）。"""
    cfg = cfg or load_feature_config()
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

    user_f = build_user_features(users, behaviors, orders, order_items, items, cfg)
    item_f = build_item_features(items, behaviors, order_items, orders, cfg)
    uitem_f = build_user_item_features(behaviors, items, cfg)

    obs_start, obs_end = observation_window(cfg, behaviors)
    tables: dict[str, dict] = {}
    for name, df in (
        ("user_features", user_f),
        ("item_features", item_f),
        ("user_item_features", uitem_f),
    ):
        path = cfg.output_dir / f"{name}.csv"
        write_csv(path, df)
        tables[name] = {"path": str(path), "rows": int(len(df)), "columns": list(df.columns)}
        logger.info("写入 %s.csv (%d 行 × %d 列)", name, len(df), df.shape[1])

    # ---- 数据字典 ----
    write_json(cfg.dictionary_path, feature_dictionary())
    logger.info("写入 feature_dictionary.json (%d 个字段)", len(feature_dictionary()))

    # ---- 运行记录（feature_version / feature_time_range / 血缘）----
    meta = {
        "feature_version": cfg.feature_version,
        "dataset_version": _dataset_version(cfg),
        "observation_window_days": cfg.observation_days,
        "feature_time_range": {"start": str(obs_start.date()), "end": str(obs_end.date())},
        "leakage_guard": "特征仅使用观察窗口内数据，未读取未来标签；静态画像为 as-of 属性。",
        "config": {
            "observation_days": cfg.observation_days,
            "obs_end": str(obs_end.date()),
            "session_gap_minutes": cfg.session_gap_minutes,
            "behavior_weights": cfg.behavior_weights,
        },
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "tables": tables,
        "dictionary": str(cfg.dictionary_path),
        "results": list(tables.keys()),
    }
    write_json(cfg.feature_meta_path, meta)
    logger.info("特征工程完成 in %ss | 输出: %s", meta["elapsed_seconds"], cfg.output_dir)
    return meta


def write_json(path, data) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _dataset_version(cfg: FeatureConfig) -> str:
    p = cfg.interim_dir / "etl_meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("dataset_version", "unknown")
        except Exception:
            return "unknown"
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="特征工程入口: 用户特征 / 商品特征 / 用户-商品交互特征 -> data/features",
    )
    parser.add_argument("--processed-dir", type=str, default=None, help="清洗数据目录（默认 data/processed）")
    parser.add_argument("--interim-dir", type=str, default=None, help="中间产物目录（默认 data/interim）")
    parser.add_argument("--output-dir", type=str, default=None, help="特征输出目录（默认 data/features）")
    parser.add_argument("--observation-days", type=int, default=None, help="观察窗口天数（默认 30）")
    parser.add_argument("--obs-end", type=str, default=None, help="观察窗口结束日 YYYY-MM-DD（默认取数据截止日）")
    parser.add_argument("--feature-version", type=str, default=None, help="特征版本（默认 1.0）")
    parser.add_argument("--session-gap-minutes", type=int, default=None, help="会话切分阈值（默认 30）")

    args = parser.parse_args(argv)
    cfg = load_feature_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
        observation_days=args.observation_days,
        obs_end=args.obs_end,
        feature_version=args.feature_version,
        session_gap_minutes=args.session_gap_minutes,
    )
    run_feature_engineering(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())