"""特征工程公共工具（Phase 8）。

- ``load_processed`` / ``write_json``：复用 ``analysis.analysis.base``；
- ``write_csv``：特征表落盘（UTF-8 with BOM，与 processed CSV 口径一致）；
- ``resolve_obs_end`` / ``observation_window``：确定观察窗口 [start, end]（两端含）；
- ``count_matrix``：按指定键聚合出的 5 种行为计数矩阵。

观察窗口规则（开发文档第 49.6 节）：
obs_end 优先取配置，其次 etl_meta 的 anchor_end_date，最后行为数据最大日期；
start = obs_end - (observation_days - 1)，保证窗口长度为 observation_days 天。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.analysis.base import load_processed, safe_div, write_json  # noqa: F401

from .config import BEHAVIOR_TYPES, FeatureConfig

# 兜底日期：与数据生成器固定截止日一致（analysis/data_generation/config.py）
_FALLBACK_END = "2026-08-31"


def write_csv(path: Path | str, df: pd.DataFrame) -> None:
    """特征表写为 CSV（UTF-8 with BOM，供 pandas 直接回读）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False, encoding="utf-8-sig")


def resolve_obs_end(cfg: FeatureConfig, behaviors: pd.DataFrame) -> pd.Timestamp:
    """确定观察窗口结束日（含）。优先级：配置 > etl_meta anchor > 数据最大日期 > 兜底。"""
    if cfg.obs_end:
        return pd.Timestamp(cfg.obs_end).normalize()
    anchor = _anchor_from_meta(cfg.interim_dir)
    if anchor:
        return pd.Timestamp(anchor).normalize()
    dates = pd.to_datetime(behaviors["event_date"], errors="coerce").dropna()
    if len(dates):
        return dates.max().normalize()
    return pd.Timestamp(_FALLBACK_END)


def _anchor_from_meta(interim_dir: Path | str) -> str | None:
    p = Path(interim_dir) / "etl_meta.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("anchor_end_date")
    except Exception:
        return None


def observation_window(cfg: FeatureConfig, behaviors: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """返回 (start, end)，窗口为闭区间，长度为 observation_days 天。"""
    end = resolve_obs_end(cfg, behaviors)
    start = end - pd.Timedelta(days=cfg.observation_days - 1)
    return start, end


def count_matrix(events: pd.DataFrame, key_cols: str | list[str], type_col: str = "behavior_type") -> pd.DataFrame:
    """返回 [key_cols(索引), 5 种行为计数] 的计数矩阵；缺失行为类型补 0。"""
    keys = [key_cols] if isinstance(key_cols, str) else list(key_cols)
    counts = events.groupby(keys + [type_col]).size().unstack(fill_value=0)
    for bt in BEHAVIOR_TYPES:
        if bt not in counts.columns:
            counts[bt] = 0
    return counts[list(BEHAVIOR_TYPES)]