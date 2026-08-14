"""推荐系统（Phase 11-14，开发文档第 49.9 ~ 49.12 节）。

- ``config``：行为权重 / 时间衰减 / 过滤 / Top-K / 内容与 Hybrid 配置；
- ``base``：BaseRecommender 统一接口 + 时间衰减 / min-max 标准化 / 过滤工具；
- ``popular``：Popular Baseline（行为加权 + 时间衰减，冷启动友好）；
- ``content``：Content-Based（分类/品牌/价格档/标签 余弦相似度）；
- ``itemcf``：Item-CF（user-item 加权矩阵 + item-item 余弦）；
- ``usercf``：User-CF（user-user 余弦 + 相似用户加权）；
- ``hybrid``：四路召回归一化后加权融合（权重可配置）；
- ``evaluate``：离线时间切分评估 + 权重实验 + 多算法对比 + 规范化结论；
- ``run``：全量入口，产物落盘 data/recommendation/。
"""

RECOMMENDATION_VERSION = "1.0"