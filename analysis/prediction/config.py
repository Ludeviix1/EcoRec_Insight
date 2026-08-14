"""购买预测配置（Phase 9，开发文档第 49.7 节）。

时间窗设计（观察窗口 + 预测窗口，见开发文档第 49.7 节 / 2128 行）：
- 观察窗口：每行样本的特征取自 ``[obs_end - (observation_days - 1), obs_end]``（两端含）；
- 预测窗口：标签取自 ``(obs_end, obs_end + label_days]``，即未来 label_days 天是否购买；
- 快照（snapshot）：在一段时间轴上以 ``snapshot_step`` 天为步长滚动生成训练样本，
  从而支持"时间切分"（train/val/test 按 obs_end 时间先后划分，杜绝未来信息泄漏）。

类别不平衡：评估不只看 Accuracy，固定输出 Precision / Recall / F1 / ROC-AUC /
PR-AUC / Confusion Matrix，并报告正样本占比（positive_rate）。

配置优先级：CLI 参数 > 环境变量 > 默认值（与 ``analysis.feature_engineering.config`` 风格一致）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

PREDICTION_VERSION = "1.0"

# 参与建模的数值特征列（与 feature_dictionary.json 中 table=user_features 字段一一对应）
PREDICTION_FEATURE_COLS: tuple[str, ...] = (
    "age", "gender_m", "gender_f", "register_days", "is_new_in_window",
    "total_behaviors", "n_pv", "n_click", "n_collect", "n_cart", "n_buy",
    "behavior_buy_ratio", "n_active_days", "active_day_ratio",
    "behaviors_per_active_day", "avg_behaviors_per_day", "n_sessions",
    "behaviors_per_session", "recency_days", "first_activity_offset_days",
    "n_distinct_items", "n_distinct_categories", "n_channels", "n_devices",
    "click_rate", "collect_rate", "cart_rate", "buy_rate",
    "paid_order_count", "paid_gmv", "avg_order_amount", "max_order_amount",
    "purchased_items", "purchased_categories", "purchase_days", "has_purchase",
)

# 不参与建模的列（主键 / 类别文本列）
DROPPED_COLS: tuple[str, ...] = ("user_id", "obs_end", "top_channel", "top_device", "label")


@dataclass(frozen=True)
class PredictionConfig:
    """购买预测全部参数。"""

    processed_dir: Path = _PROJECT_ROOT / "data" / "processed"
    interim_dir: Path = _PROJECT_ROOT / "data" / "interim"
    output_dir: Path = _PROJECT_ROOT / "data" / "prediction"
    observation_days: int = 30                  # 观察窗口天数
    label_days: int = 7                         # 预测窗口天数（未来 N 天是否购买）
    snapshot_step: int = 7                      # 快照步长（天），控制样本时点密度
    snapshot_ends: tuple[str, ...] = ()         # 手动指定快照结束日（默认由数据时间范围推导）
    train_ratio: float = 0.6                    # 时间切分：最早的一段快照为训练集
    val_ratio: float = 0.2                      # 中间为验证集
    test_ratio: float = 0.2                     # 最晚为测试集
    random_state: int = 42                      # 可复现随机种子
    session_gap_minutes: int = 30               # 会话切分阈值（与 Phase 8 特征一致）
    behavior_weights: dict[str, int] = field(default_factory=lambda: {"pv": 1, "click": 2, "collect": 3, "cart": 4, "buy": 5})
    lr_max_iter: int = 2_000                    # LogisticRegression 迭代上限
    rf_n_estimators: int = 200                  # RandomForest 树数量
    rf_max_depth: int | None = None             # RandomForest 最大深度
    prediction_version: str = PREDICTION_VERSION

    @property
    def meta_path(self) -> Path:
        return self.output_dir / "prediction_meta.json"

    @property
    def metrics_path(self) -> Path:
        return self.output_dir / "metrics.json"

    @property
    def importance_path(self) -> Path:
        return self.output_dir / "feature_importance.json"


def load_prediction_config(**overrides) -> PredictionConfig:
    """构建购买预测配置，优先级：CLI 参数 > 环境变量 > 默认值。"""

    def _path(name: str, default: Path) -> Path:
        return Path(overrides[name]) if overrides.get(name) else Path(os.environ.get(name, str(default)))

    observation_days = overrides.get("observation_days") or int(os.environ.get("PRED_OBS_DAYS", "30"))
    label_days = overrides.get("label_days") or int(os.environ.get("PRED_LABEL_DAYS", "7"))
    step = overrides.get("snapshot_step") or int(os.environ.get("PRED_SNAPSHOT_STEP", "7"))
    train_ratio = overrides.get("train_ratio") or float(os.environ.get("PRED_TRAIN_RATIO", "0.6"))
    val_ratio = overrides.get("val_ratio") or float(os.environ.get("PRED_VAL_RATIO", "0.2"))
    test_ratio = overrides.get("test_ratio") or float(os.environ.get("PRED_TEST_RATIO", "0.2"))
    seed = overrides.get("random_state") or int(os.environ.get("PRED_SEED", "42"))
    version = overrides.get("prediction_version") or os.environ.get("PRED_VERSION", PREDICTION_VERSION)
    snapshot_ends = overrides.get("snapshot_ends") or ()

    return PredictionConfig(
        processed_dir=_path("processed_dir", _PROJECT_ROOT / "data" / "processed"),
        interim_dir=_path("interim_dir", _PROJECT_ROOT / "data" / "interim"),
        output_dir=_path("output_dir", _PROJECT_ROOT / "data" / "prediction"),
        observation_days=int(observation_days),
        label_days=int(label_days),
        snapshot_step=int(step),
        snapshot_ends=tuple(snapshot_ends) if snapshot_ends else (),
        train_ratio=float(train_ratio),
        val_ratio=float(val_ratio),
        test_ratio=float(test_ratio),
        random_state=int(seed),
        lr_max_iter=int(overrides["lr_max_iter"]) if overrides.get("lr_max_iter") else int(os.environ.get("PRED_LR_MAX_ITER", "2000")),
        rf_n_estimators=int(overrides["rf_n_estimators"]) if overrides.get("rf_n_estimators") else int(os.environ.get("PRED_RF_N_ESTIMATORS", "200")),
        rf_max_depth=overrides.get("rf_max_depth") or (int(os.environ["PRED_RF_MAX_DEPTH"]) if os.environ.get("PRED_RF_MAX_DEPTH") else None),
        prediction_version=str(version),
    )