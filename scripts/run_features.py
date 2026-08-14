"""Phase 8 特征工程入口脚本（开发文档第 49.6 节）。

运行：
    python scripts/run_features.py                        # 默认读取 data/processed，输出到 data/features
    python scripts/run_features.py --observation-days 30  # 观察窗口可调
    python scripts/run_features.py --obs-end 2026-08-31   # 窗口结束日可调

产物：
    data/features/user_features.csv       用户级特征（Phase 9 购买预测消费）
    data/features/item_features.csv       商品级特征（Phase 12 Content-Base 消费）
    data/features/user_item_features.csv  用户-商品交互特征（召回 / 交叉特征）
    data/features/feature_dictionary.json 特征数据字典
    data/features/feature_meta.json       运行记录（feature_version / feature_time_range）
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.feature_engineering.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())