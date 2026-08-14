"""Phase 15 推荐评估（开发文档第 49.13 节 / 36 节）。

必须严格使用时间切分（历史行为 → train，未来行为 → test，推荐只用 train 信息），
对比 5 种算法：Popular / ItemCF / UserCF / Content / Hybrid，
输出每算法的 Precision@10 / Recall@10 / F1@10 / HitRate@10 / NDCG@10 / Coverage。

结论必须基于评估指标：若 Hybrid 未优于 Popular baseline，不强行声称 Hybrid 更好。

运行：
    python scripts/run_evaluation.py
    python scripts/run_evaluation.py --k 10 --test-ratio 0.25 --max-users 3000

产物写入 data/recommendation/：
    evaluation_summary.csv             规范列名（Algorithm, Precision@10, ... Coverage）
    evaluation_summary.json            5 算法指标明细 + 诚实结论（基于离线指标）
"""

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
    compare_algorithms,
    conclude_vs_baseline,
    report_table,
)

logger = logging.getLogger("analysis.recommendation.evaluation")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Phase 15: 5 算法离线时间切分评估")
    parser.add_argument("--processed-dir", type=str, default=None)
    parser.add_argument("--interim-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--hybrid-weights", type=str, default=None)
    parser.add_argument("--n-neighbors", type=int, default=None)
    parser.add_argument("--k", type=int, default=DEFAULT_EVAL_K)
    parser.add_argument("--test-ratio", type=float, default=DEFAULT_TEST_RATIO)
    parser.add_argument("--max-users", type=int, default=DEFAULT_MAX_USERS)
    args = parser.parse_args(argv)

    cfg = load_recommend_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
        hybrid_weights=args.hybrid_weights,
        n_neighbors=args.n_neighbors,
    )

    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")

    t0 = time.perf_counter()
    summary, details = compare_algorithms(
        behaviors, items, orders, order_items, cfg=cfg,
        algorithms=["popular", "itemcf", "usercf", "content", "hybrid"],
        k=args.k, test_ratio=args.test_ratio, max_users=args.max_users,
    )
    table = report_table(summary, k=args.k)
    table.to_csv(cfg.output_dir / "evaluation_summary.csv", index=False, encoding="utf-8-sig")

    conclusion = conclude_vs_baseline(details, k=args.k, baseline="popular")
    doc = {
        "task": "evaluation",
        "method": "严格时间切分（历史→train，未来→test），推荐只用 train 信息",
        "test_ratio": args.test_ratio,
        "k": args.k,
        "max_users": args.max_users,
        "algorithms": list(summary["algorithm"]),
        "results": {r["algorithm"]: {c: r[c] for c in ("precision@k", "recall@k", "f1@k",
                                                        "hit_rate@k", "ndcg@k", "coverage@k")}
                    for _, r in summary.iterrows()},
        "baseline": "popular",
        "conclusion": conclusion,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }
    (cfg.output_dir / "evaluation_summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("评估完成 | %s", conclusion)
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
