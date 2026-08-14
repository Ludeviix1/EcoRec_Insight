# data 数据分层说明

> 以下"开发文档第 X 节"均指向项目最新版开发文档 `开发文档2.2.md`（如有更新版本以最新版为准）。

| 目录 | 含义 | 内容 |
|---|---|---|
| `raw/` | 原始数据（Phase 3 产物，只读） | 数据生成器直接输出的模拟数据（users / items / user_behaviors / orders / order_items CSV）+ `data_meta.json` |
| `interim/` | 中间数据（Phase 4 产物） | 数据质量报告 `data_quality_report.json`、ETL 运行记录 `etl_meta.json` |
| `processed/` | 加工数据（Phase 4 产物） | 清洗去重后的最终数据集（6 张 CSV），供 MySQL 入库与 Phase 5+ 全量分析使用 |
| `analysis/` | 分析结果（Phase 5/6/7 产物） | 结构化 JSON（用户规模 / DAU·WAU·MAU / 行为 / 活跃时间 / GMV / 商品·分类·品牌排行 / 漏斗 / 留存 / Cohort / RFM / 生命周期 / 购买路径 / 商品生命周期 / 价格 / 渠道 / 设备 / 关联规则 / 用户分群 / 用户画像 / 商品画像 / 业务发现），供 FastAPI 直接复用 |
| `prediction/` | 购买预测模型 | LR/RF 模型 + 快照样本集 + 评估指标 + 特征重要性 + 运行记录（Phase 9） |
| `churn/` | 流失预测模型 | LR/RF 模型 + 流失样本集 + 评估指标 + 特征重要性 + churn_predictions.csv（user_id/churn_probability/risk_level）+ 运行记录（Phase 10） |
| `recommendation/` | 推荐结果 | popular_model.joblib + 全量热度分 + 全体活跃用户 Top-K + 运行记录（Phase 11） |

约定：

- 数据目录内生成的业务文件全部被 `.gitignore` 忽略，仅保留 `.gitkeep`。
- 所有数据必须可复现：`RANDOM_STATE = 42`，生成脚本记录数据版本信息。
- 数据量可配置（默认见 `开发文档2.2.md` 第 12 节，低配电脑建议 用户 2,000 / 商品 1,000 / 行为 100,000 / 订单 10,000）。
- ETL（Phase 4）：`python scripts/run_etl.py` 把 `raw/` 清洗为 `processed/` 并写出质检报告，`refresh` 模式自动清空 MySQL 核心表重载，重复运行不会产生重复订单/行为。
- 基础分析（Phase 5）：`python scripts/run_analysis.py` 读取 `processed/`，把结果输出到 `analysis/` 下的 JSON 文件，并记录 `analysis_meta.json`。
- 留存 / Cohort / RFM（Phase 6）：随 `run_analysis.py` 一并产出（`retention.json` / `cohort.json` / `rfm.json`）；RFM 评分分桶与分群规则为可配置项（见 `analysis/analysis/rfm.py` 的 `RfmConfig`）。
- 深度业务分析（Phase 7）：随 `run_analysis.py` 一并产出（`lifecycle.json` / `purchase_path.json` / `item_lifecycle.json` / `price.json` / `channel.json` / `device.json` / `association.json` / `user_segments.json` / `user_profile.json` / `item_profile.json` / `findings.json`）。要点：生命周期规则可配置（`LifecycleConfig`）；购买路径按会话切分且不伪造 search；关联规则分商品级与分类级（数据商品级稀疏）；用户分群为 KMeans（`user_segmentation`，可配置 n_clusters）；业务发现统一为"现象→证据→可能原因→业务建议"并注明数据为模拟数据。
- 特征工程（Phase 8）：`python scripts/run_features.py` 读取 `processed/`，输出到 `features/`（`user_features.csv` / `item_features.csv` / `user_item_features.csv` / `feature_dictionary.json` / `feature_meta.json`）。要点：特征只使用 Observation Window（默认过去 30 天，可配置 `FEAT_OBS_DAYS` / `FEAT_OBS_END`，窗口结束日含端点）内的行为/订单聚合，不读取未来标签；`feature_meta.json` 记录 `feature_version` / `feature_time_range` / dataset 血缘；每个字段都在 `feature_dictionary.json` 数据字典中有说明，保证可复现。
- 购买预测（Phase 9）：`python scripts/run_prediction.py` 读取 `processed/`，输出到 `prediction/`（`snapshot_dataset.csv` / `model_logistic_regression.pkl` / `model_random_forest.pkl` / `metrics.json` / `feature_importance.json` / `prediction_meta.json`）。要点：按 `snapshot_step` 天（默认 7，可配置 `PRED_SNAPSHOT_STEP`）在数据时间轴上滚动生成快照样本，每行=1 用户×1 快照：特征只用观察窗口 `[obs_end-29, obs_end]` 内数据，标签=预测窗口 `(obs_end, obs_end+7]` 内是否有 paid 订单（`PRED_OBS_DAYS` / `PRED_LABEL_DAYS` 可配）；train/val/test 按 `obs_end` 时间先后切分（非随机，杜绝泄漏）；类别不平衡不以 Accuracy 为准，输出 Precision/Recall/F1/ROC-AUC/PR-AUC/混淆矩阵与 `positive_rate`；模型 LR（标准化+类别平衡）+ RF（类别平衡），`prediction_meta.json` 记录模型/时间窗/切分/血缘。
- 流失预测（Phase 10）：`python scripts/run_churn.py` 读取 `processed/`，输出到 `churn/`（`churn_dataset.csv` / `model_logistic_regression.pkl` / `model_random_forest.pkl` / `metrics.json` / `feature_importance.json` / `churn_predictions.csv` / `churn_meta.json`）。要点：与购买预测同构但标签不同——只保留观察窗口 `[obs_end-29, obs_end]` 内活跃（≥1 条行为）的用户为候选人群；流失定义=预测窗口 `(obs_end, obs_end+30]` 内无关键行为（默认 buy/collect/cart，可配置 `CHURN_KEY_BEHAVIORS`）且无 paid 订单，否则未流失（`CHURN_OBS_DAYS` / `CHURN_LABEL_DAYS` 可配，默认 30/30）；输出 `user_id / churn_probability / risk_level`（low/medium/high，阈值 `CHURN_RISK_LOW` / `CHURN_RISK_HIGH` 默认 0.3/0.7）；`churn_meta.json` 必须记录并说明观察窗口 / 预测窗口 / 流失定义；评估口径与 Phase 9 一致（时间切分防泄漏 + PR-AUC/ROC-AUC/混淆矩阵）。
- 推荐（Phase 11）：`python scripts/run_recommendation.py` 读取 `processed/`，输出到 `recommendation/`（`popular_model.joblib` / `popular_items.csv` / `popular_recommendations.csv` / `recommendation_meta.json`）。要点：热度分=各行为类型（pv/click/collect/cart/buy）加权聚合（默认权重 1/2/3/4/5，可配置 `REC_WEIGHTS`，JSON 或 `pv:1,...`）并叠加指数时间衰减（半衰期 `REC_HALF_LIFE_DAYS` 默认 7 天，`decay=0.5**（days_ago/half_life）`）；各行为分量 max-normalization 到 [0,1]、最终热度分 min-max 到 [0,1]；过滤已购买 / 已下架 / 不存在 / 重复（开发文档第 35.7 节）；新用户冷启动直接返回全局热门 Top-K；统一接口 `recommend(user_id, top_k)`，每条推荐含 score 与 reason；模型用 joblib 保存供 FastAPI 加载（开发文档第 47 节）。
