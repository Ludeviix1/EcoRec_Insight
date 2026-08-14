"""Phase 10 流失预测入口脚本（开发文档第 49.8 节）。

运行：
    python scripts/run_churn.py                              # 默认读取 data/processed，输出到 data/churn
    python scripts/run_churn.py --label-days 30              # 预测窗口可调
    python scripts/run_churn.py --risk-high-threshold 0.7    # 风险等级阈值可调

产物：
    data/churn/churn_dataset.csv         滚动快照流失样本集（特征 + churn label）
    data/churn/model_logistic_regression.pkl  Logistic Regression 模型
    data/churn/model_random_forest.pkl    Random Forest 模型
    data/churn/metrics.json              评估指标（含 PR-AUC / 混淆矩阵）
    data/churn/feature_importance.json   特征重要性 / 系数解释
    data/churn/churn_predictions.csv     预测输出（user_id / churn_probability / risk_level）
    data/churn/churn_meta.json           运行记录（观察窗口 / 预测窗口 / 流失定义 / 风险等级）
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.churn.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())