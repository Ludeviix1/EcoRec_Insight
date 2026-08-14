"""特征工程模块（Phase 8，开发文档第 49.6 节）。

对应流程：

    过去30天行为（Observation Window）
            ↓
    生成用户 / 商品 / 交互特征
            ↓
    feature_version / feature_time_range

模块划分：
- ``config``       特征配置（观察窗口 / 特征版本 / 行为权重可配置）；
- ``base``         公共工具（processed 读取、观察窗口、行为计数矩阵、CSV/JSON 落盘）；
- ``dictionary``   特征数据字典（字段说明，随特征一起落盘）；
- ``user_features``     用户级特征（供 Phase 9 购买预测）；
- ``item_features``     商品级特征（供 Phase 12 Content-Base / 商品画像）；
- ``user_item_features`` 用户-商品交互特征（供召回 / 交叉特征）；
- ``run``          特征工程全量入口（CLI）。

防泄漏硬性约束（开发文档第 49.6 节）：
- 特征只允许使用观察窗口内的数据；
- 不得读取未来标签信息（Phase 9 才构造 label）；
- 特征计算纯函数 + 固定观察窗口 => 可复现；
- 每个特征字段都有数据字典。
"""

from .config import BEHAVIOR_TYPES, DEFAULT_BEHAVIOR_WEIGHTS, FEATURE_VERSION, FeatureConfig, load_feature_config

__all__ = [
    "BEHAVIOR_TYPES",
    "DEFAULT_BEHAVIOR_WEIGHTS",
    "FEATURE_VERSION",
    "FeatureConfig",
    "load_feature_config",
]