# 电商用户行为分析与智能推荐平台

面向秋招求职展示的综合型 Python 数据分析、机器学习、推荐系统与数据应用平台。

项目目标：从一批原始数据出发，经过**数据生成 → 数据清洗 → ETL → 数据存储 → 数据质量 → 基础分析 → 深度业务分析 → 用户画像 → 用户分群 → 预测建模 → 推荐系统 → 推荐评估 → FastAPI → Vue3/ECharts → 测试 → 部署 → 项目文档**的完整数据闭环，最终形成真实可运行、可解释、可评估、可展示的数据应用。

> 完整开发规格以最新版开发文档为准，见 `开发文档2.2.md`。

## 核心原则

- **P0（必须实现）**：数据生成/清洗/ETL/质量检查，全量分析体系，购买/流失预测，Popular/Item-CF/User-CF/Content/Hybrid 推荐，FastAPI + Vue3 + ECharts + Docker。
- **P1（加分项）**：用户价值预测、CTR 预测、多路召回 + LightGBM 排序、推荐多样性、Redis 缓存。
- **P2（仅设计，不实现代码）**：Kafka / Spark / Flink——只在 `docs/architecture.md` 中给出架构设计用于面试展示。

严格遵守：时间切分防数据泄漏（前 80% 训练 / 后 20% 测试）、`RANDOM_STATE = 42` 可复现、API 分层 `Router → Service → Repository → Database`、禁止伪实现（`pass` / mock 数据）。

## 目录结构

``` text
backend/    FastAPI 服务（app/core, models, schemas, routers, services, repositories, middleware, tests）
analysis/   数据分析链路（data_generation, cleaning, etl, quality, analysis, feature_engineering, models, recommendation）
data/       数据分层（raw / interim / processed / features）
sql/        MySQL 建表与索引脚本
frontend/   Vue3 + ECharts 前端（Phase 17 实现）
tests/      集成测试
docs/       架构与技术文档
scripts/    一键运行脚本（init_db / generate_data / run_etl / run_all）
docker/     Docker 编排资源
models/     训练产物（joblib 模型 + metadata）
```

## 当前进度

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | 需求和架构、仓库/目录、README | ✅ 完成 |
| 1 | Python + FastAPI 初始化：config / logging / database / health API | ✅ 完成 |
| 2 | MySQL 建表（12 张表 + 主键/唯一键/外键逻辑/索引） | ✅ 完成 |
| 3 | 数据生成器（含业务规律模拟） | ✅ 完成 |
| 4 | 数据质量 + ETL（清洗/质检/报告/Processed/MySQL 批量入库，可重复执行） | ✅ 完成 |
| 5 | 基础分析（用户规模 / DAU·WAU·MAU / 行为 / 活跃时间 / GMV / 商品·分类·品牌排行 / 漏斗） | ✅ 完成 |
| 6 | 留存 + Cohort + RFM（留存口径 / cohort 起点 / RFM 规则可配置 / 分群可解释） | ✅ 完成 |
| 7 | 深度业务分析（生命周期 / 购买路径 / 商品生命周期 / 价格 / 渠道 / 设备 / 关联规则 / 用户分群 / 用户画像 / 商品画像 / 业务发现） | ✅ 完成 |
| 8 | 特征工程（Observation Window 过去30天：用户 / 商品 / 用户-商品交互特征 + 数据字典 + feature_version / feature_time_range，防泄漏） | ✅ 完成 |
| 9 | 购买预测（滚动快照：过去30天特征 -> 未来7天是否购买；LR + RF；Precision/Recall/F1/ROC-AUC/PR-AUC/混淆矩阵；时间切分防泄漏；模型+metadata+特征重要性） | ✅ 完成 |
| 10 | 流失预测（观察窗口活跃用户 + 未来30天无关键行为/购买 => 流失；LR + RF；输出 user_id/churn_probability/risk_level；时间切分防泄漏；文档化观察窗口/预测窗口/流失定义） | ✅ 完成 |
| 11 | Popular Baseline 推荐（PV/Click/Collect/Cart/Buy 加权 + 时间衰减 + 标准化 + 权重可配置；过滤已购买/下架/重复；冷启动支持；统一 recommend 接口） | ✅ 完成 |
| 12 | 权重实验（实验A 1/2/3/4/5、实验B 1/2/4/6/8、实验C 1/2/3/5/10；严格时间切分 train/test；Precision@10/Recall@10/F1@10/HitRate@10/NDCG@10/Coverage；最优权重依据离线实验而非主观判断） | ✅ 完成 |
| 13 | Content-Based 推荐（category/brand/price_range/item tags 构造商品向量 + 余弦相似度；用户历史商品→相似商品→分数累加→过滤→Top-K；已购买/下架过滤；冷启动商品与新用户兜底） | ✅ 完成 |
| 14 | Hybrid 推荐（ItemCF + UserCF + Popular + Content 四路召回归一化到 [0,1] 后加权融合，权重可配置；baseline vs hybrid 离线对比并依据评估指标给结论） | ✅ 完成 |
| 15+ | 详见 `开发文档2.2.md` 第 49 节 Phase 规划 | 待开发 |

## 快速开始（current 阶段）

``` bash
# 1. 创建虚拟环境（Windows）
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r backend/requirements.txt
pip install -r analysis/requirements.txt

# 3. 配置环境变量
copy backend\.env.example backend\.env

# 4. 初始化数据库（建库建表 + 索引；--reset 可删库重建）
python scripts/init_db.py

# 5. 生成模拟数据
python scripts/generate_data.py                    # 默认 low 规模 (2K 用户)
python scripts/generate_data.py --scale standard   # 标准规模 (10K 用户)

# 6. ETL：清洗 -> 质检报告 -> Processed CSV -> MySQL（refresh 自动清空重载，幂等）
python scripts/run_etl.py                          # 默认写 MySQL
python scripts/run_etl.py --skip-mysql             # 只产出清洗数据 + 质检报告

#   产物
#   data/processed/            6 张清洗后 CSV（Phase 5+ 分析消费）
#   data/interim/data_quality_report.json   数据质量报告
#   data/interim/etl_meta.json              ETL 运行记录（dataset_version 等）

# 7. 分析：读取 processed，输出结构化 JSON 到 data/analysis（Phase 5 基础 + Phase 6 留存/RFM + Phase 7 深度分析）
python scripts/run_analysis.py
python scripts/run_analysis.py --top-n 20     # 排行 TOP N 可调

#   产物（供后续 FastAPI 直接复用）
#   data/analysis/user_scale.json            用户规模
#   data/analysis/dau_wau_mau.json           DAU / WAU / MAU
#   data/analysis/behavior.json              行为分析
#   data/analysis/active_time.json           活跃时间
#   data/analysis/gmv.json                   GMV / 订单 / 客单价 / ARPU
#   data/analysis/item_ranking.json          商品排行
#   data/analysis/category_ranking.json      分类排行
#   data/analysis/brand_ranking.json         品牌排行
#   data/analysis/funnel.json                转化漏斗
#   data/analysis/retention.json             留存（次日/3/7/14/30 日）
#   data/analysis/cohort.json                Cohort 留存矩阵（热力图）
#   data/analysis/rfm.json                   RFM 用户价值分群
#   data/analysis/lifecycle.json             用户生命周期（规则可配置）
#   data/analysis/purchase_path.json         用户购买路径（会话切分）
#   data/analysis/item_lifecycle.json        商品生命周期
#   data/analysis/price.json                 价格分析（自动分箱）
#   data/analysis/channel.json               渠道质量对比（非 ROI）
#   data/analysis/device.json                设备分析
#   data/analysis/association.json           商品/分类关联规则（Apriori）
#   data/analysis/user_segments.json         KMeans 用户分群（业务解释）
#   data/analysis/user_profile.json          用户画像
#   data/analysis/item_profile.json          商品画像
#   data/analysis/findings.json              业务发现（现象→证据→原因→建议，注明模拟数据）
#   data/analysis/analysis_meta.json         运行记录（analysis_version 3.0）

# 8. 特征工程：读取 processed，输出用户/商品/用户-商品交互特征（Phase 8，Observation Window 过去30天）
python scripts/run_features.py
python scripts/run_features.py --observation-days 30     # 观察窗口可调
python scripts/run_features.py --obs-end 2026-08-31      # 窗口结束日可调

#   产物（供 Phase 9 购买预测 / Phase 12 内容推荐 / 召回直接复用）
#   data/features/user_features.csv           用户级特征（1 行/用户）
#   data/features/item_features.csv           商品级特征（1 行/商品）
#   data/features/user_item_features.csv      用户-商品交互特征（仅窗口内有行为的对）
#   data/features/feature_dictionary.json     特征数据字典
#   data/features/feature_meta.json           运行记录（feature_version / feature_time_range）

# 9. 购买预测：滚动快照（过去30天特征 -> 未来7天是否购买），LR + RF 训练评估（Phase 9）
python scripts/run_prediction.py
python scripts/run_prediction.py --label-days 7         # 预测窗口可调
python scripts/run_prediction.py --rf-n-estimators 300  # 模型参数可调

#   产物
#   data/prediction/snapshot_dataset.csv        滚动快照样本集（特征 + label）
#   data/prediction/model_logistic_regression.pkl  Logistic Regression 模型
#   data/prediction/model_random_forest.pkl      Random Forest 模型
#   data/prediction/metrics.json                 评估指标（PR-AUC / ROC-AUC / 混淆矩阵）
#   data/prediction/feature_importance.json      特征重要性 / 系数解释
#   data/prediction/prediction_meta.json         运行记录（时间窗 / 时间切分 / 防泄漏）

# 10. 流失预测：观察窗口活跃用户 -> 未来30天是否流失（Phase 10）
python scripts/run_churn.py
python scripts/run_churn.py --label-days 30          # 预测窗口可调
python scripts/run_churn.py --risk-high-threshold 0.7  # 风险等级阈值可调

#   产物
#   data/churn/churn_dataset.csv         滚动快照流失样本集（特征 + churn label）
#   data/churn/model_logistic_regression.pkl  Logistic Regression 模型
#   data/churn/model_random_forest.pkl      Random Forest 模型
#   data/churn/metrics.json                 评估指标（PR-AUC / ROC-AUC / 混淆矩阵）
#   data/churn/feature_importance.json      特征重要性 / 系数解释
#   data/churn/churn_predictions.csv        预测输出（user_id / churn_probability / risk_level）
#   data/churn/churn_meta.json              运行记录（观察窗口 / 预测窗口 / 流失定义 / 风险等级）

# 11. Popular Baseline 推荐：行为加权 + 时间衰减（Phase 11）
python scripts/run_recommendation.py
python scripts/run_recommendation.py --half-life-days 3      # 时间衰减可调
python scripts/run_recommendation.py --behavior-weights pv:1,click:2,collect:3,cart:4,buy:5  # 权重可配置
python scripts/run_recommendation.py --top-k 10              # 每用户推荐条数

#   产物
#   data/recommendation/popular_model.joblib        模型（供 FastAPI 加载）
#   data/recommendation/popular_items.csv           全量商品热度分
#   data/recommendation/popular_recommendations.csv 全体活跃用户 Top-K
#   data/recommendation/recommendation_meta.json    运行记录（公式/衰减/过滤/冷启动）

# 12. 权重实验（Phase 12）：离线时间切分评估三组权重
python scripts/run_weight_experiment.py              # 默认 k=10, test_ratio=0.25, 最多3000用户
python scripts/run_weight_experiment.py --k 10 --test-ratio 0.25 --max-users 3000

#   产物
#   data/recommendation/weight_experiment.csv        三组权重 @K 指标对比表
#   data/recommendation/weight_experiment.json       明细 + 最优权重结论（依据离线实验）

# 13. Content-Based 推荐（Phase 13）：分类/品牌/价格档/标签 余弦相似度
python scripts/run_content.py
python scripts/run_content.py --price-bins 5        # 价格分箱数
python scripts/run_content.py --top-k 10 --sim-top 30   # Top-K 与每种子相似商品数

#   产物
#   data/recommendation/content_model.joblib            模型（供 FastAPI 加载）
#   data/recommendation/content_recommendations.csv     全体活跃用户 Top-K
#   data/recommendation/content_meta.json               运行记录（特征/相似度/过滤/冷启动）

# 14. Hybrid 推荐 + baseline vs hybrid 对比（Phase 14）：四路召回归一化融合
python scripts/run_hybrid.py
python scripts/run_hybrid.py --hybrid-weights 'itemcf:0.25,usercf:0.15,popular:0.30,content:0.30'  # 融合权重可配
python scripts/run_hybrid.py --n-neighbors 50 --k 10 --test-ratio 0.25   # User-CF 邻居数与评估参数

#   产物
#   data/recommendation/hybrid_model.joblib             模型（供 FastAPI 加载）
#   data/recommendation/hybrid_recommendations.csv      全体活跃用户 Top-K
#   data/recommendation/hybrid_meta.json                运行记录（公式/融合/过滤/冷启动）
#   data/recommendation/algo_comparison.csv             5 算法离线指标对比表
#   data/recommendation/algo_comparison.json            对比明细 + 结论（依据评估指标）

# 15. 启动后端
uvicorn backend.app.main:app --reload

# 16. 验证
curl http://127.0.0.1:8000/api/health
# 预期: {"code":0,"message":"success","data":{"status":"ok"}}
# 交互式文档: http://127.0.0.1:8000/docs

# 17. 运行测试
python -m pytest backend/tests -v                     # 后端测试
python -m pytest tests/test_data_generation.py -v     # Phase 3 数据生成测试
python -m pytest tests/test_phase4_quality_etl.py -v  # Phase 4 数据质量 + ETL 测试
python -m pytest tests/test_phase5_analysis.py -v     # Phase 5 基础分析测试
python -m pytest tests/test_phase6_analysis.py -v     # Phase 6 留存/Cohort/RFM 测试
python -m pytest tests/test_phase7_analysis.py -v     # Phase 7 深度业务分析测试
python -m pytest tests/test_phase8_features.py -v     # Phase 8 特征工程测试
python -m pytest tests/test_phase9_prediction.py -v   # Phase 9 购买预测测试
python -m pytest tests/test_phase10_churn.py -v       # Phase 10 流失预测测试
python -m pytest tests/test_phase11_popular.py -v     # Phase 11 Popular 推荐测试
python -m pytest tests/test_phase12_weight_experiment.py -v  # Phase 12 权重实验测试
python -m pytest tests/test_phase13_content.py -v      # Phase 13 Content-Based 测试
python -m pytest tests/test_phase14_hybrid.py -v       # Phase 14 Hybrid 测试
```

## 技术栈

Python 3.11+ · FastAPI · SQLAlchemy 2.x · MySQL 8.x · Pandas · scikit-learn · Vue3 · ECharts · Docker · pytest

（P1：LightGBM/XGBoost、Redis；P2 仅设计：Kafka/Spark/Flink）