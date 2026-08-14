"""购买预测（Phase 9，开发文档第 49.7 节）。

- ``config``：时间窗 / 切分比例 / 模型参数配置；
- ``data``：滚动快照样本集（观察窗口特征 + 未来 7 天购买标签，防泄漏）；
- ``model``：LR / RF 训练与评估（Precision/Recall/F1/ROC-AUC/PR-AUC/混淆矩阵）；
- ``run``：全量入口，产物落盘 data/prediction/。
"""

PREDICTION_VERSION = "1.0"
