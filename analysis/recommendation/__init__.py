"""推荐系统（Phase 11，开发文档第 49.9 节起）。

- ``config``：行为权重 / 时间衰减 / 过滤 / Top-K 配置；
- ``base``：BaseRecommender 统一接口 + 时间衰减 / min-max 标准化 / 过滤工具；
- ``popular``：Popular Baseline（行为加权 + 时间衰减，冷启动友好）；
- ``run``：全量入口，产物落盘 data/recommendation/。
"""

RECOMMENDATION_VERSION = "1.0"