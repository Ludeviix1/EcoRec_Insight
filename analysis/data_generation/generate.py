"""数据生成编排器（Phase 3）。

职责：按依赖顺序调用各生成器 -> 裁剪 schema 列 -> 写 CSV 到 data/raw/ -> 写 meta。
可复现：固定种子 + 固定截止日；可重复执行（覆盖输出）。
不连数据库（入库是 Phase 4 ETL 的职责）。

运行：``python scripts/generate_data.py``（或 ``python -m analysis.data_generation.generate``）
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DataGenConfig, load_config
from .generators import (
    CATEGORY_COLUMNS,
    ITEM_COLUMNS,
    USER_COLUMNS,
    generate_categories,
    generate_items,
    generate_users,
)
from .behaviors import generate_behaviors_and_orders

logger = logging.getLogger("data_generation")

# 数据版本（生成规则变更时递增），写入 meta 便于追溯
DATA_SCHEMA_VERSION = "1.0"


def run_generation(cfg: DataGenConfig | None = None, *, log: bool = True) -> dict:
    """执行全量数据生成，返回统计信息 dict。

    cfg 为 None 时使用默认配置（low 规模）。
    """
    cfg = cfg or load_config()
    if log:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stdout,
        )

    rng = np.random.default_rng(cfg.random_state)
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    logger.info("data generation start: users=%d items=%d target_behaviors=%d seed=%d end_date=%s",
                cfg.n_users, cfg.n_items, cfg.n_behaviors, cfg.random_state, cfg.data_end_date)

    # 1. 分类
    categories = generate_categories(rng, cfg)
    _save_csv(categories[CATEGORY_COLUMNS], output_dir / "categories.csv", log=False)
    logger.info("categories: %d rows", len(categories))

    # 2. 用户
    users = generate_users(rng, cfg)
    _save_csv(users[USER_COLUMNS], output_dir / "users.csv", log=False)
    logger.info("users: %d rows", len(users))

    # 3. 商品
    items = generate_items(rng, cfg, categories)
    _save_csv(items[ITEM_COLUMNS], output_dir / "items.csv", log=False)
    logger.info("items: %d rows (active=%d)",
                len(items), int((items["status"] == 1).sum()))

    # 4. 行为 + 订单
    behaviors, orders, order_items = generate_behaviors_and_orders(rng, cfg, users, items, categories)
    _save_csv(behaviors, output_dir / "user_behaviors.csv", log=False)
    _save_csv(orders, output_dir / "orders.csv", log=False)
    _save_csv(order_items, output_dir / "order_items.csv", log=False)
    logger.info("behaviors: %d rows | orders: %d | order_items: %d",
                len(behaviors), len(orders), len(order_items))

    # 5. 行为类型分布（用于校验漏斗形状）
    btype_counts = behaviors["behavior_type"].value_counts().to_dict()

    # 6. 写 meta（开发文档第 47 节：记录种子 / 时间范围 / 数据版本 / 指标）
    elapsed = round(time.perf_counter() - t0, 2)
    meta = {
        "schema_version": DATA_SCHEMA_VERSION,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "random_state": cfg.random_state,
        "data_end_date": str(cfg.data_end_date),
        "behavior_window_days": cfg.behavior_window_days,
        "registration_window_days": cfg.registration_window_days,
        "counts": {
            "users": len(users),
            "categories": len(categories),
            "items": len(items),
            "user_behaviors": len(behaviors),
            "orders": len(orders),
            "order_items": len(order_items),
        },
        "behavior_type_counts": btype_counts,
        "value_tier_ratio": list(cfg.value_tier_ratio),
        "heat_level_ratio": list(cfg.heat_level_ratio),
        "elapsed_seconds": elapsed,
        "files": [
            "categories.csv", "users.csv", "items.csv",
            "user_behaviors.csv", "orders.csv", "order_items.csv",
        ],
    }
    meta_path = output_dir / "data_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("data generation done in %ss, output: %s", elapsed, output_dir)
    logger.info("behavior funnel: %s", btype_counts)
    return meta


def _save_csv(df: pd.DataFrame, path: Path, *, log: bool = True) -> None:
    """保存 CSV（UTF-8 带 BOM，便于 Excel 直接打开中文；index 不写入）。"""
    df.to_csv(path, index=False, encoding="utf-8-sig")
    if log:
        logger.info("saved %s (%d rows)", path.name, len(df))


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：支持 --scale / --users / --items / --behaviors / --seed / --output-dir。"""
    import argparse

    parser = argparse.ArgumentParser(description="生成电商模拟数据（Phase 3）")
    parser.add_argument("--scale", choices=["low", "standard", "large"], help="规模预设：low/standard/large")
    parser.add_argument("--users", type=int, help="用户数（覆盖预设）")
    parser.add_argument("--items", type=int, help="商品数（覆盖预设）")
    parser.add_argument("--behaviors", type=int, help="目标行为数（覆盖预设）")
    parser.add_argument("--seed", type=int, help="随机种子（默认 42）")
    parser.add_argument("--output-dir", type=str, help="输出目录（默认 data/raw）")
    args = parser.parse_args(argv)

    cfg = load_config(
        scale=args.scale,
        n_users=args.users,
        n_items=args.items,
        n_behaviors=args.behaviors,
        random_state=args.seed,
        output_dir=args.output_dir,
    )
    run_generation(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
