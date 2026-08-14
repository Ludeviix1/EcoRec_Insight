"""流失预测模型（Phase 10，开发文档第 49.8 节）。

直接复用 ``analysis.prediction.model`` 的时间切分 / 训练评估链路（特征列相同，
评估口径一致），避免重复造轮子（开发文档第 54 节规则 19：优先复用已有代码）。
"""

from __future__ import annotations

from analysis.prediction.model import (  # noqa: F401  # 复用：时间切分 / 训练评估 / 保存
    _feature_importance,
    _safe_metrics,
    save_model,
    time_split,
    train_and_evaluate,
    write_json,
)

__all__ = [
    "time_split",
    "train_and_evaluate",
    "_safe_metrics",
    "_feature_importance",
    "save_model",
    "write_json",
]