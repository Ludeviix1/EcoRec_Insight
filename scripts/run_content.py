"""Phase 13 Content-Based 推荐入口脚本（开发文档第 49.11 节）。

运行：
    python scripts/run_content.py
    python scripts/run_content.py --price-bins 5        # 价格分箱数
    python scripts/run_content.py --top-k 10 --sim-top 30

产物：
    data/recommendation/content_model.joblib            模型（供 FastAPI 加载）
    data/recommendation/content_recommendations.csv     全体活跃用户 Top-K
    data/recommendation/content_meta.json               运行记录（特征/相似度/过滤/冷启动）
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.recommendation.config import load_recommend_config  # noqa: E402
from analysis.recommendation.run import build_content  # noqa: E402


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Content-Based: 分类/品牌/价格档/标签 余弦相似度 -> data/recommendation")
    parser.add_argument("--processed-dir", type=str, default=None)
    parser.add_argument("--interim-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--behavior-weights", type=str, default=None,
                        help='行为权重，JSON 或 "pv:1,click:2,collect:3,cart:4,buy:5"')
    parser.add_argument("--half-life-days", type=float, default=None, help="种子时间衰减半衰期（默认 7）")
    parser.add_argument("--top-k", type=int, default=None, help="每个用户推荐条数（默认 10）")
    parser.add_argument("--price-bins", type=int, default=None, help="价格分箱数（默认 4）")
    parser.add_argument("--sim-top", type=int, default=None, help="每种子取前 N 相似商品（默认 20）")
    args = parser.parse_args()

    cfg = load_recommend_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
        behavior_weights=args.behavior_weights,
        half_life_days=args.half_life_days,
        top_k=args.top_k,
        n_price_bins=args.price_bins,
        sim_top=args.sim_top,
    )
    build_content(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())