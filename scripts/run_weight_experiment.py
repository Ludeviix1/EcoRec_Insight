"""Phase 12 权重实验 CLI（开发文档第 49.10 节 / 36 节）。

用法示例:
    python scripts/run_weight_experiment.py
    python scripts/run_weight_experiment.py --k 10 --test-ratio 0.25

产物写入 data/recommendation/：
    weight_experiment.csv     各实验 @K 指标对比表
    weight_experiment.json    明细 + 最优权重结论
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.feature_engineering.base import load_processed  # noqa: E402
from analysis.recommendation.config import load_recommend_config  # noqa: E402
from analysis.recommendation.evaluate import (  # noqa: E402
    DEFAULT_EVAL_K,
    DEFAULT_MAX_USERS,
    DEFAULT_TEST_RATIO,
    choose_best,
    run_weight_experiment,
)

logger = logging.getLogger("analysis.recommendation.evaluate")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Popular 权重离线实验（历史→train，未来→test）")
    parser.add_argument("--processed-dir", type=str, default=None, help="清洗数据目录（默认 data/processed）")
    parser.add_argument("--interim-dir", type=str, default=None, help="中间产物目录（默认 data/interim）")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录（默认 data/recommendation）")
    parser.add_argument("--k", type=int, default=DEFAULT_EVAL_K, help="Top-K（默认 10）")
    parser.add_argument("--test-ratio", type=float, default=DEFAULT_TEST_RATIO, help="未来行为的测试占比（默认 0.25）")
    parser.add_argument("--max-users", type=int, default=DEFAULT_MAX_USERS, help="评估用户数上限（默认 3000）")
    args = parser.parse_args(argv)

    cfg = load_recommend_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
    )
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")
    logger.info("加载 processed | items=%d behaviors=%d", len(items), len(behaviors))
    t0 = time.perf_counter()

    summary, details = run_weight_experiment(
        behaviors, items, orders, order_items, cfg=cfg,
        k=args.k, test_ratio=args.test_ratio, max_users=args.max_users,
    )

    best = choose_best(summary)
    best_row = summary[summary["experiment"] == best].iloc[0]
    out_csv = Path(args.output_dir or cfg.output_dir) / "weight_experiment.csv"
    summary.to_csv(out_csv, index=False, encoding="utf-8-sig")

    doc = {
        "task": "weight_experiment",
        "algorithm": "popular",
        "method": "严格时间切分（历史→train，未来→test），推荐只用 train 信息，test 仅评价",
        "test_ratio": args.test_ratio,
        "k": args.k,
        "max_users": args.max_users,
        "variants": [
            {"experiment": row["experiment"],
             "weights": {"pv": row["pv"], "click": row["click"],
                         "collect": row["collect"], "cart": row["cart"], "buy": row["buy"]}}
            for _, row in summary.iterrows()
        ],
        "results": {e: d for e, d in details.items()},
        "best_experiment": best,
        "best_weights": {
            "pv": float(best_row["pv"]), "click": float(best_row["click"]),
            "collect": float(best_row["collect"]), "cart": float(best_row["cart"]),
            "buy": float(best_row["buy"]),
        },
        "selection_criterion": (
            "依据离线实验结果选择：NDCG@10 最高（并列时 Recall@10 更高）。"
            "不以主观『感觉权重更合理』为依据。"
        ),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "note": "若最优权重与当前默认 1/2/3/4/5 不同，应更新 RecommendConfig 默认权重",
    }
    out_json = Path(args.output_dir or cfg.output_dir) / "weight_experiment.json"
    out_json.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("完成 | best=%s ndcg@%d=%.4f | CSV=%s", best, args.k, best_row["ndcg@k"], out_csv.name)
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())