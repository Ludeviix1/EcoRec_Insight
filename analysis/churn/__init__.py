"""流失预测（Phase 10，开发文档第 49.8 节）。

- ``config``：时间窗 / 流失定义（关键行为）/ 风险等级阈值配置；
- ``data``：滚动快照流失样本集（观察窗口特征 + 未来 30 天流失标签，防泄漏）；
- ``model``：复用购买预测的 LR / RF 训练评估链路；
- ``run``：全量入口，产物落盘 data/churn/（含 churn_predictions.csv）。
"""

CHURN_VERSION = "1.0"