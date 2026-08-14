"""Phase 14 Hybrid 推荐 + baseline vs hybrid 离线对比（开发文档第 49.12 节 / 36 节）。

运行：
    python scripts/run_hybrid.py
    python scripts/run_hybrid.py --hybrid-weights 'itemcf:0.25,usercf:0.15,popular:0.30,content:0.30'
    python scripts/run_hybrid.py --k 10 --test-ratio 0.25 --max-users 3000

产物写入 data/recommendation/：
    hybrid_model.joblib                    模型（供 FastAPI 加载）
    hybrid_recommendations.csv             全体活跃用户 Top-K
    hybrid_meta.json                       运行记录（公式/融合/过滤/冷启动）
    algo_comparison.csv                    baseline vs hybrid 离线指标对比表
    algo_comparison.json                   对比明细 + 结论（基于评估指标）
"""

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
)
from analysis.recommendation.run import build_hybrid  # noqa: E402

logger = logging.getLogger("analysis.recommendation.hybrid")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    import argparse
    parser = argparse.ArgumentParser(description="Hybrid: ItemCF+UserCF+Popular+Content 加权融合")
    parser.add_argument("--processed-dir", type=str, default=None)
    parser.add_argument("--interim-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--behavior-weights", type=str, default=None)
    parser.add_argument("--half-life-days", type=float, default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--hybrid-weights", type=str, default=None,
                        help='混合权重 JSON 或 "itemcf:0.25,usercf:0.15,popular:0.30,content:0.30"')
    parser.add_argument("--n-neighbors", type=int, default=None, help="User-CF 相似用户数（默认 50）")
    parser.add_argument("--price-bins", type=int, default=None)
    parser.add_argument("--sim-top", type=int, default=None)
    parser.add_argument("--k", type=int, default=DEFAULT_EVAL_K, help="离线评估 Top-K（默认 10）")
    parser.add_argument("--test-ratio", type=float, default=DEFAULT_TEST_RATIO)
    parser.add_argument("--max-users", type=int, default=DEFAULT_MAX_USERS)
    args = parser.parse_args(argv)

    cfg = load_recommend_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
        behavior_weights=args.behavior_weights,
        half_life_days=args.half_life_days,
        top_k=args.top_k,
        hybrid_weights=args.hybrid_weights,
        n_neighbors=args.n_neighbors,
        n_price_bins=args.price_bins,
        sim_top=args.sim_top,
    )

    # 1) baseline vs hybrid 离线对比（结论依据评估指标）
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
    summary.to_csv(cfg.output_dir / "algo_comparison.csv", index=False, encoding="utf-8-sig")

    base = details.get("popular", {})
    hyb = details.get("hybrid", {})
    better = (hyb.get("ndcg@k", 0) or 0) > (base.get("ndcg@k", 0) or 0)
    conclusion = (
        f"Hybrid NDCG@{args.k}={hyb.get('ndcg@k')} vs Popular baseline={base.get('ndcg@k')} → "
        + ("Hybrid 更优（基于离线指标）" if better
           else "Hybrid 未优于 Popular baseline，不强行声称混合更好（基于离线指标）")
    )
    cmp_doc = {
        "task": "algo_comparison",
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
    (cfg.output_dir / "algo_comparison.json").write_text(
        json.dumps(cmp_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("对比完成 | %s | %s", "popular vs hybrid", conclusion)
    print(summary.to_string(index=False))

    # 2) 构建并保存 Hybrid 模型（供 FastAPI）
    build_hybrid(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())