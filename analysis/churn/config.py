"""流失预测配置（Phase 10，开发文档第 49.8 节）。

时间窗设计：
- 观察窗口：每行样本的特征取自 ``[obs_end - (observation_days - 1), obs_end]``（两端含）；
- 预测窗口：标签取自 ``(obs_end, obs_end + label_days]``，即未来 label_days 天是否"仍有关键行为/购买"；
- 快照（snapshot）：以 ``snapshot_step`` 天为步长滚动生成训练样本，
  支持"时间切分"（train/val/test 按 obs_end 时间先后划分，杜绝未来信息泄漏）。

流失定义（开发文档第 32 节 / 49.8 节）：
- 候选人群：观察窗口内"活跃"的用户（窗口内至少有 1 条任何行为）；
- 流失(churn=1)：候选人群在预测窗口内没有关键行为（buy/collect/cart）且没有 paid 订单；
- 否则 churn=0（用户未来 30 天仍有关键行为或购买，即"未流失"）。

输出：user_id / churn_probability / risk_level（low/medium/high），risk_level 由可配置阈值得到。

配置优先级：CLI 参数 > 环境变量 > 默认值（与 ``analysis.prediction.config`` 风格一致）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

CHURN_VERSION = "1.0"

# 关键行为类型：预测窗口内出现即视为"用户仍活跃"（pv/click 过于低意图，不计入）
DEFAULT_CHURN_KEY_BEHAVIORS: tuple[str, ...] = ("buy", "collect", "cart")


@dataclass(frozen=True)
class ChurnConfig:
    """流失预测全部参数。"""

    processed_dir: Path = _PROJECT_ROOT / "data" / "processed"
    interim_dir: Path = _PROJECT_ROOT / "data" / "interim"
    output_dir: Path = _PROJECT_ROOT / "data" / "churn"
    observation_days: int = 30                  # 观察窗口天数
    label_days: int = 30                        # 预测窗口天数（未来 N 天是否仍活跃）
    snapshot_step: int = 7                      # 快照步长（天）
    snapshot_ends: tuple[str, ...] = ()         # 手动指定快照结束日（默认由数据时间范围推导）
    train_ratio: float = 0.6                    # 时间切分：最早的一段快照为训练集
    val_ratio: float = 0.2                      # 中间为验证集
    test_ratio: float = 0.2                     # 最晚为测试集
    random_state: int = 42                      # 可复现随机种子
    session_gap_minutes: int = 30               # 会话切分阈值（与 Phase 8 特征一致）
    behavior_weights: dict[str, int] = field(default_factory=lambda: {"pv": 1, "click": 2, "collect": 3, "cart": 4, "buy": 5})
    churn_key_behaviors: tuple[str, ...] = DEFAULT_CHURN_KEY_BEHAVIORS  # 关键行为类型
    risk_low_threshold: float = 0.3             # risk_level: p < low  => low
    risk_high_threshold: float = 0.7            # risk_level: p > high => high，否则 medium
    lr_max_iter: int = 2_000                    # LogisticRegression 迭代上限
    rf_n_estimators: int = 200                  # RandomForest 树数量
    rf_max_depth: int | None = None             # RandomForest 最大深度
    churn_version: str = CHURN_VERSION

    @property
    def meta_path(self) -> Path:
        return self.output_dir / "churn_meta.json"

    @property
    def metrics_path(self) -> Path:
        return self.output_dir / "metrics.json"

    @property
    def importance_path(self) -> Path:
        return self.output_dir / "feature_importance.json"

    @property
    def predictions_path(self) -> Path:
        return self.output_dir / "churn_predictions.csv"


def load_churn_config(**overrides) -> ChurnConfig:
    """构建流失预测配置，优先级：CLI 参数 > 环境变量 > 默认值。"""

    def _path(name: str, default: Path) -> Path:
        return Path(overrides[name]) if overrides.get(name) else Path(os.environ.get(name, str(default)))

    observation_days = overrides.get("observation_days") or int(os.environ.get("CHURN_OBS_DAYS", "30"))
    label_days = overrides.get("label_days") or int(os.environ.get("CHURN_LABEL_DAYS", "30"))
    step = overrides.get("snapshot_step") or int(os.environ.get("CHURN_SNAPSHOT_STEP", "7"))
    train_ratio = overrides.get("train_ratio") or float(os.environ.get("CHURN_TRAIN_RATIO", "0.6"))
    val_ratio = overrides.get("val_ratio") or float(os.environ.get("CHURN_VAL_RATIO", "0.2"))
    test_ratio = overrides.get("test_ratio") or float(os.environ.get("CHURN_TEST_RATIO", "0.2"))
    seed = overrides.get("random_state") or int(os.environ.get("CHURN_SEED", "42"))
    version = overrides.get("churn_version") or os.environ.get("CHURN_VERSION", CHURN_VERSION)
    snapshot_ends = overrides.get("snapshot_ends") or ()
    key_behaviors = (
        tuple(overrides["churn_key_behaviors"])
        if overrides.get("churn_key_behaviors")
        else tuple(
            b.strip() for b in os.environ.get("CHURN_KEY_BEHAVIORS", ",".join(DEFAULT_CHURN_KEY_BEHAVIORS)).split(",")
        )
    )

    return ChurnConfig(
        processed_dir=_path("processed_dir", _PROJECT_ROOT / "data" / "processed"),
        interim_dir=_path("interim_dir", _PROJECT_ROOT / "data" / "interim"),
        output_dir=_path("output_dir", _PROJECT_ROOT / "data" / "churn"),
        observation_days=int(observation_days),
        label_days=int(label_days),
        snapshot_step=int(step),
        snapshot_ends=tuple(snapshot_ends) if snapshot_ends else (),
        train_ratio=float(train_ratio),
        val_ratio=float(val_ratio),
        test_ratio=float(test_ratio),
        random_state=int(seed),
        lr_max_iter=int(overrides["lr_max_iter"]) if overrides.get("lr_max_iter") else int(os.environ.get("CHURN_LR_MAX_ITER", "2000")),
        rf_n_estimators=int(overrides["rf_n_estimators"]) if overrides.get("rf_n_estimators") else int(os.environ.get("CHURN_RF_N_ESTIMATORS", "200")),
        rf_max_depth=overrides.get("rf_max_depth") or (int(os.environ["CHURN_RF_MAX_DEPTH"]) if os.environ.get("CHURN_RF_MAX_DEPTH") else None),
        risk_low_threshold=overrides.get("risk_low_threshold") or float(os.environ.get("CHURN_RISK_LOW", "0.3")),
        risk_high_threshold=overrides.get("risk_high_threshold") or float(os.environ.get("CHURN_RISK_HIGH", "0.7")),
        churn_key_behaviors=key_behaviors,
        churn_version=str(version),
    )