"""特征工程配置（Phase 8，开发文档第 49.6 节）。

要点：
- ``observation_days``：Observation Window 长度（默认过去 30 天），
  窗口 = [obs_end - (observation_days - 1), obs_end]，两端含；
- ``obs_end``：窗口结束日（含），默认取 etl_meta 的 anchor_end_date，
  缺失时回退到行为数据的最大日期（生成器固定截止日为 2026-08-31，可复现）；
- ``feature_version``：特征版本，随 feature_meta.json 一并记录；
- ``behavior_weights``：行为权重（默认 pv:1/click:2/collect:3/cart:4/buy:5，
  与开发文档第 35.2 节、``analysis.analysis.item.ranking`` 保持一致），可配置。

配置优先级：CLI 参数 > 环境变量 > 默认值（与 ``analysis.etl.config`` 风格一致）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_VERSION = "1.0"

# 允许的行为类型与默认行为权重
BEHAVIOR_TYPES: tuple[str, ...] = ("pv", "click", "collect", "cart", "buy")
DEFAULT_BEHAVIOR_WEIGHTS: dict[str, int] = {"pv": 1, "click": 2, "collect": 3, "cart": 4, "buy": 5}


@dataclass(frozen=True)
class FeatureConfig:
    """特征工程全部参数。"""

    processed_dir: Path = _PROJECT_ROOT / "data" / "processed"
    interim_dir: Path = _PROJECT_ROOT / "data" / "interim"
    output_dir: Path = _PROJECT_ROOT / "data" / "features"
    observation_days: int = 30                    # 观察窗口长度（天），默认过去 30 天
    obs_end: str | None = None                    # 观察窗口结束日（含）；None=自动取数据截止日
    feature_version: str = FEATURE_VERSION
    session_gap_minutes: int = 30                 # 会话切分阈值（分钟）
    behavior_weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_BEHAVIOR_WEIGHTS))

    @property
    def feature_meta_path(self) -> Path:
        return self.output_dir / "feature_meta.json"

    @property
    def dictionary_path(self) -> Path:
        return self.output_dir / "feature_dictionary.json"


def load_feature_config(**overrides) -> FeatureConfig:
    """构建特征配置，优先级：CLI 参数 > 环境变量 > 默认值。"""

    def _path(name: str, default: Path) -> Path:
        return Path(overrides[name]) if overrides.get(name) else Path(os.environ.get(name, str(default)))

    observation_days = overrides.get("observation_days") or int(os.environ.get("FEAT_OBS_DAYS", "30"))
    obs_end = overrides.get("obs_end") or os.environ.get("FEAT_OBS_END")
    version = overrides.get("feature_version") or os.environ.get("FEAT_VERSION", FEATURE_VERSION)
    gap = overrides.get("session_gap_minutes") or int(os.environ.get("FEAT_SESSION_GAP", "30"))
    weights = overrides.get("behavior_weights") or dict(DEFAULT_BEHAVIOR_WEIGHTS)

    return FeatureConfig(
        processed_dir=_path("processed_dir", _PROJECT_ROOT / "data" / "processed"),
        interim_dir=_path("interim_dir", _PROJECT_ROOT / "data" / "interim"),
        output_dir=_path("output_dir", _PROJECT_ROOT / "data" / "features"),
        observation_days=int(observation_days),
        obs_end=str(obs_end) if obs_end else None,
        feature_version=str(version),
        session_gap_minutes=int(gap),
        behavior_weights=dict(weights),
    )