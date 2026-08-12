# 系统总体架构

> 对应开发文档 2.1 第 2 节，落地实现范围 P0 + P1。

## 1. 总体架构（P0 + P1 落地）

``` text
                         ┌──────────────────────┐
                         │   用户行为/订单数据   │
                         └──────────┬───────────┘
                                    │
                         数据生成 / 数据采集
                                    ▼
                         ┌──────────────────────┐
                         │       Raw Data       │
                         └──────────┬───────────┘
                                    │
                              数据质量检查
                                    ▼
                         ┌──────────────────────┐
                         │ Cleaning / ETL       │
                         └──────────┬───────────┘
                                    ▼
                              MySQL 数据仓库
                                    ▼
                         ┌──────────────────────┐
                         │    数据分析层        │
                         │ 用户/商品/GMV/漏斗/  │
                         │ 留存/Cohort/RFM/路径 │
                         │ /生命周期/关联/渠道  │
                         └──────────┬───────────┘
                                    ▼
                         ┌──────────────────────┐
                         │      特征工程层       │
                         └──────────┬───────────┘
                   ┌────────────────┴────────────────┐
                   ▼                                 ▼
          ┌──────────────────┐             ┌──────────────────┐
          │ 预测模型(购买/   │             │ 推荐系统         │
          │ 流失，P1:CTR/价值)│             │ Popular/ItemCF/  │
          └────────┬─────────┘             │ UserCF/Content/  │
                   │                       │ Hybrid(P1:多路召回/排序)│
                   │                       └────────┬─────────┘
                   └────────────────┬──────────────┘
                                    ▼
                              模型评估层
                                    ▼
                              FastAPI Service
                          ┌─────────┴─────────┐
                          ▼                   ▼
                       MySQL          Redis(P1，可选)
                          └─────────┬─────────┘
                                    ▼
                              Vue3 + ECharts
                                    ▼
                              数据分析平台
```

## 2. 各层职责

| 层 | 职责 | 对应目录 |
|---|---|---|
| 数据生成 | 按业务规律模拟用户/商品/行为/订单（用户偏好、商品热度、行为链、时间规律） | `analysis/data_generation` |
| 数据质量 | 完整性/唯一性/一致性/合法性/时间检查，输出 `data_quality_report.json` | `analysis/quality` |
| ETL | Raw → 清洗 → 转换 → 质检 → 特征 → MySQL，批量插入、可重复执行 | `analysis/etl`、`analysis/cleaning` |
| 数据仓库 | MySQL 6 张核心表 + 画像/分群/推荐/预测扩展表 | `sql` |
| 数据分析 | 用户/商品/GMV/漏斗/留存/Cohort/RFM/生命周期/路径/关联/价格/渠道/设备 | `analysis/analysis/*` |
| 特征工程 | user / item / user-item / context 四类特征 | `analysis/feature_engineering` |
| 预测建模 | 购买预测、流失预测（P1：价值、CTR） | `analysis/models` |
| 推荐系统 | Popular / ItemCF / UserCF / Content / Hybrid，可插拔统一接口 | `analysis/recommendation` |
| 服务层 | FastAPI Router → Service → Repository → Database 强制分层 | `backend/app` |
| 展示层 | Vue3 + ECharts，所有图表数据来自 API | `frontend` |

## 3. 技术选型理由

- **Python + Pandas**：数据规模为百万级行为记录，单机内存处理即可，不需要分布式框架。
- **MySQL 8.x**：关系型数仓，支撑画像/分群/推荐结果落库与 API 查询。
- **FastAPI + SQLAlchemy 2.x**：异步友好、自动 OpenAPI 文档、类型安全。
- **scikit-learn / mlxtend**：LR/RF 等 P0 模型与 Apriori 关联规则，开箱即用。
- **Vue3 + ECharts**：组件化前端，ECharts 提供 Line/Bar/Funnel/Heatmap 等图表。
- **pytest**：数据/分析/模型/推荐/API 五类测试。

## 4. 当前数据规模下为什么不用 Kafka / Spark / Flink（P2 设计）

按文档规划，数据规模为：用户万级、商品数千、行为百万级、订单十万级。该量级下：
- 单机 Pandas 处理行为表约需 GB 级内存，耗时分钟级，完全可接受；
- ETL 为离线批量任务，无实时性要求；
- Spark 的价值在千万级数据才体现，Flink 的价值在实时计算场景才体现。

结论：**在当前规模下引入 Kafka/Spark/Flink 的开发与运维成本 > 实际收益**，因此 P2 仅保留设计。

## 5. 数据量增长 100 倍的演进路径（面试第 40 题素材）

| 阈值 | 触发信号 | 迁移方案 |
|---|---|---|
| 行为数据 > 千万级 | 离线 ETL 超过小时级 | 离线 ETL/画像/特征/批量推荐迁移至 **Spark**（Spark SQL + DataFrame 批处理） |
| 需要实时指标 | 要求秒级 PV/活跃/热门/GMV | **Flink** 窗口计算（滚动/滑动窗口）替代离线日统计 |
| 实时推荐 | 行为事件需在秒级影响推荐结果 | **Kafka** 作为消息总线：`Simulator → Kafka(topic: user_behavior / order_event) → Consumer → Redis → FastAPI → Dashboard`，实时特征灌入 Redis 供推荐读取 |
| 存储层 | 结果集过大 | 维度表放 MySQL，行为明细/画像快照放 Hive/对象存储 |

**迁移路径示例**（实时链路）：

``` text
Frontend / Simulator → Kafka → Consumer → Redis → FastAPI → Dashboard
```

实时指标：实时 PV、实时活跃数、实时热门商品、实时订单、实时 GMV。

## 6. 关键工程约定

- 统一响应格式：`{"code": 0, "message": "success", "data": {...}}`，code=0 表示成功。
- 可复现：`RANDOM_STATE = 42`，记录数据版本/特征版本/模型版本/参数/指标。
- 防数据泄漏：预测与推荐评估严格执行时间切分（前 80% 训练 / 后 20% 测试）。
- API 分层：`Router → Service → Repository → Database`，禁止业务逻辑写在 Router。
- 推荐性能：离线训练 → 保存 joblib 模型/相似度矩阵 → API 启动时加载，禁止请求时重训练。
- 配置：全部走 `.env`，禁止密码写入代码。
- 日志：API request / ETL / 数据质量 / 模型训练/加载 / 推荐 / 延迟 / 错误。