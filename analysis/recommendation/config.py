"""推荐系统配置（Phase 11，开发文档第 49.9 节 / 35.1 节）。

Popular Baseline 热度分（开发文档第 49.9 节 / 35.1 节）：
    score = w_pv*pv_score + w_click*click_score + w_collect*collect_score
          + w_cart*cart_score + w_buy*buy_score
其中各行为分量已做 max-normalization 到 [0,1]（避免权重对比被淹没），
并叠加时间衰减；最终热度分再 min-max 到 [0,1] 便于跨策略比较。

时间衰减（time_decay）：
    以参考日（默认行为数据最大日期）为基准，行为越早权重越低：
    decay = 0.5 ** (days_ago / half_life_days)，half_life_days 可配置。

过滤（开发文档第 35.7 节）：
    - 已购买商品（该用户 paid 订单明细）
    - 已下架商品（items.status != 1）
    - 不存在商品 / 重复商品

冷启动（开发文档第 35.6 节）：新用户直接给全局热门 Top-K（Popular 天然支持冷启动）。

配置优先级：CLI 参数 > 环境变量 > 默认值。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

RECOMMENDATION_VERSION = "1.0"

DEFAULT_BEHAVIOR_WEIGHTS: dict[str, float] = {"pv": 1.0, "click": 2.0, "collect": 3.0, "cart": 4.0, "buy": 5.0}
DEFAULT_HALF_LIFE_DAYS: int = 7          # 时间衰减半衰期（天）
DEFAULT_TOP_K: int = 10


@dataclass(frozen=True)
class RecommendConfig:
    """推荐系统全部参数（Phase 11 起用于 Popular，后续 Phase 复用）。"""

    processed_dir: Path = _PROJECT_ROOT / "data" / "processed"
    interim_dir: Path = _PROJECT_ROOT / "data" / "interim"
    output_dir: Path = _PROJECT_ROOT / "data" / "recommendation"
    behavior_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BEHAVIOR_WEIGHTS))
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS     # 时间衰减半衰期（天）
    as_of_date: str | None = None                       # 热度参考日（默认=行为数据最大日期）
    top_k: int = DEFAULT_TOP_K
    filter_purchased: bool = True                       # 过滤已购买
    filter_off_shelf: bool = True                       # 过滤已下架
    recommend_version: str = RECOMMENDATION_VERSION

    @property
    def meta_path(self) -> Path:
        return self.output_dir / "recommendation_meta.json"

    @property
    def model_path(self) -> Path:
        return self.output_dir / "popular_model.joblib"


def _parse_weights(raw: str) -> dict[str, float]:
    """解析行为权重：支持 JSON 或 "pv:1,click:2,...,buy:5"。"""
    raw = raw.strip()
    if not raw:
        return dict(DEFAULT_BEHAVIOR_WEIGHTS)
    if raw.startswith("{"):
        try:
            return {k: float(v) for k, v in json.loads(raw).items()}
        except Exception:
            pass
    out: dict[str, float] = {}
    for item in raw.split(","):
        if ":" in item:
            k, v = item.split(":", 1)
            out[k.strip()] = float(v.strip())
    return out or dict(DEFAULT_BEHAVIOR_WEIGHTS)


def load_recommend_config(**overrides) -> RecommendConfig:
    """构建推荐配置，优先级：CLI 参数 > 环境变量 > 默认值。"""

    def _path(name: str, default: Path) -> Path:
        return Path(overrides[name]) if overrides.get(name) else Path(os.environ.get(name, str(default)))

    weights = (
        _parse_weights(overrides["behavior_weights"])
        if overrides.get("behavior_weights")
        else _parse_weights(os.environ.get("REC_WEIGHTS", ""))
    )
    half_life = overrides.get("half_life_days") or float(os.environ.get("REC_HALF_LIFE_DAYS", str(DEFAULT_HALF_LIFE_DAYS)))
    top_k = overrides.get("top_k") or int(os.environ.get("REC_TOP_K", str(DEFAULT_TOP_K)))
    as_of = overrides.get("as_of_date") or os.environ.get("REC_AS_OF_DATE")
    version = overrides.get("recommend_version") or os.environ.get("REC_VERSION", RECOMMENDATION_VERSION)

    return RecommendConfig(
        processed_dir=_path("processed_dir", _PROJECT_ROOT / "data" / "processed"),
        interim_dir=_path("interim_dir", _PROJECT_ROOT / "data" / "interim"),
        output_dir=_path("output_dir", _PROJECT_ROOT / "data" / "recommendation"),
        behavior_weights=weights,
        half_life_days=float(half_life),
        as_of_date=str(as_of) if as_of else None,
        top_k=int(top_k),
        filter_purchased=bool(overrides.get("filter_purchased", os.environ.get("REC_FILTER_PURCHASED", "1") in ("1", "true", "True", "yes"))),
        filter_off_shelf=bool(overrides.get("filter_off_shelf", os.environ.get("REC_FILTER_OFF_SHELF", "1") in ("1", "true", "True", "yes"))),
        recommend_version=str(version),
    )