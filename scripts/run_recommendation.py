"""Phase 11 Popular Baseline 推荐入口脚本（开发文档第 49.9 节）。

运行：
    python scripts/run_recommendation.py          # 默认读取 data/processed，输出到 data/recommendation
    python scripts/run_recommendation.py --half-life-days 3    # 时间衰减可调
    python scripts/run_recommendation.py --behavior-weights pv:1,click:2,collect:3,cart:4,buy:5  # 权重可配

产物：
    data/recommendation/popular_model.joblib                  模型（供 FastAPI 加载）
    data/recommendation/popular_items.csv                     全量商品热度分
    data/recommendation/popular_recommendations.csv           全体活跃用户 Top-K
    data/recommendation/recommendation_meta.json              运行记录（公式/衰减/过滤/冷启动）
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.recommendation.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())