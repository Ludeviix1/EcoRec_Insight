"""购买预测数据集构建（Phase 9，开发文档第 49.7 节）。

流程：
    data/processed 六张清洗 CSV
        ↓ 滚动快照（snapshot_step 天步长）
    每个快照 obs_end 生成一行/用户：
        特征:观察窗口 [obs_end-29, obs_end]（复用 Phase 8 用户特征）
        标签:预测窗口 (obs_end, obs_end+7] 内是否有 paid 订单
        ↓
    data/prediction/snapshot_dataset.csv（含 label / obs_end）

防泄漏：
- 特征只读观察窗口内行为/订单，标签只读预测窗口内 paid 订单，两窗口互不重叠；
- 同一用户的不同快照在时间上顺序生成，测试集永远使用更晚的快照；
- 不读取 any 未来信息。
"""

from __future__ import annotations

import pandas as pd

from analysis.feature_engineering.base import load_processed  # noqa: F401  # 复用入口
from analysis.feature_engineering.config import FeatureConfig
from analysis.feature_engineering.user_features import build_user_features

from .config import PredictionConfig

# 每行固定输出列：特征 + 标签 + 快照身份
_OUT_COLS = ("user_id", "obs_end", "label")


def resolve_dataset_range(
    cfg: PredictionConfig, behaviors: pd.DataFrame
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """返回可用的 (最早 obs_end, 最晚 obs_end)，保证观察窗口与预测窗口都落在数据范围内。"""
    dates = pd.to_datetime(behaviors["event_date"], errors="coerce").dropna().dt.normalize()
    orders_hint = pd.Timestamp("2026-08-31")  # 数据固定截止日，见 data_generation.config.DEFAULT_DATA_END_DATE
    data_min = dates.min().normalize() if len(dates) else orders_hint - pd.Timedelta(days=60)
    data_max = min(dates.max().normalize() if len(dates) else orders_hint, orders_hint)
    # 最早 obs_end：观察窗口 [obs_end-29, obs_end] 需完全落在数据范围内
    earliest = data_min + pd.Timedelta(days=cfg.observation_days - 1)
    # 最晚 obs_end：预测窗口 (obs_end, obs_end+label_days] 需完全落在数据范围内
    latest = data_max - pd.Timedelta(days=cfg.label_days)
    if earliest > latest:
        raise ValueError(
            f"数据时间范围({data_min.date()}~{data_max.date()})不足以容纳观察窗口"
            f"({cfg.observation_days}天)+预测窗口({cfg.label_days}天)"
        )
    return earliest, latest


def snapshot_obs_ends(cfg: PredictionConfig, behaviors: pd.DataFrame) -> list[pd.Timestamp]:
    """生成快照 obs_end 序列（升序）。支持手动指定 cfg.snapshot_ends；否则按步长滚动。"""
    if cfg.snapshot_ends:
        ends = sorted(pd.Timestamp(x).normalize() for x in cfg.snapshot_ends)
        return ends
    earliest, latest = resolve_dataset_range(cfg, behaviors)
    step = max(cfg.snapshot_step, 1)
    return [earliest + pd.Timedelta(days=i * step) for i in range((latest - earliest).days // step + 1) if (earliest + pd.Timedelta(days=i * step)) <= latest]


def _label_buyers(orders: pd.DataFrame, obs_end: pd.Timestamp, label_days: int) -> set[str]:
    """预测窗口 (obs_end, obs_end+label_days] 内有 paid 订单的用户集合。"""
    orders = orders.copy()
    orders["order_time"] = pd.to_datetime(orders["order_time"], errors="coerce")
    end = obs_end + pd.Timedelta(days=label_days)
    hit = orders[(orders["order_time"] > obs_end) & (orders["order_time"] <= end) & (orders["status"] == "paid")]
    return set(hit["user_id"])


def build_snapshot_dataset(
    users, behaviors, orders, order_items, items, cfg: PredictionConfig | None = None
) -> pd.DataFrame:
    """构建滚动快照样本集（一行/用户/快照，含特征列 + label + obs_end）。

    特征列与 Phase 8 user_features 完全一致，仅额外追加 label 与 obs_end。
    """
    cfg = cfg or PredictionConfig()
    ends = snapshot_obs_ends(cfg, behaviors)
    frames: list[pd.DataFrame] = []
    for obs_end in ends:
        fcfg = FeatureConfig(
            processed_dir=cfg.processed_dir,
            interim_dir=cfg.interim_dir,
            observation_days=cfg.observation_days,
            obs_end=str(obs_end.date()),
            session_gap_minutes=cfg.session_gap_minutes,
            behavior_weights=cfg.behavior_weights,
        )
        feats = build_user_features(users, behaviors, orders, order_items, items, fcfg)
        buyers = _label_buyers(orders, obs_end, cfg.label_days)
        feats["label"] = feats["user_id"].isin(buyers).astype(int)
        feats["obs_end"] = obs_end.date().isoformat()
        # 断言特征窗口与标签窗口不重叠（防泄漏护栏）
        frames.append(feats)
    out = pd.concat(frames, ignore_index=True)
    return out[list(_OUT_COLS) + [c for c in out.columns if c not in _OUT_COLS]]