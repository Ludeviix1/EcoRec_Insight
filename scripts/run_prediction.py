"""Phase 9 购买预测入口脚本（开发文档第 49.7 节）。

运行：
    python scripts/run_prediction.py                        # 默认读取 data/processed，输出到 data/prediction
    python scripts/run_prediction.py --label-days 7         # 预测窗口可调
    python scripts/run_prediction.py --rf-n-estimators 300  # 模型参数可调

产物：
    data/prediction/snapshot_dataset.csv        滚动快照样本集（特征 + label）
    data/prediction/model_logistic_regression.pkl  Logistic Regression 模型
    data/prediction/model_random_forest.pkl      Random Forest 模型
    data/prediction/metrics.json                评估指标（含 PR-AUC / 混淆矩阵）
    data/prediction/feature_importance.json     特征重要性 / 系数解释
    data/prediction/prediction_meta.json        运行记录（时间窗 / 防泄漏 / 切分 / 版本血缘）
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.prediction.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())