"""流失预测数据集构建（Phase 10，开发文档第 49.8 节）。

流程：
    data/processed 六张清洗 CSV
        ↓ 滚动快照（snapshot_step 天步长）
    每个快照 obs_end 生成一行/用户（仅观察窗口内活跃的用户）：
        特征：观察窗口 [obs_end-29, obs_end]（复用 Phase 8 用户特征）
        标签：churn = 预测窗口 (obs_end, obs_end+30] 内无关键行为(默认 buy/collect/cart) 且无 paid 订单
        ↓
    data/churn/churn_dataset.csv（含 label / obs_end）

流失定义（开发文档第 32 节）：
    在观察窗口内活跃（窗口内至少有行为），但未来 30 天没有关键行为/购买 => churn=1。
    未在观察窗口内活跃的用户不进入 churn 样本集（他们不在"可能流失"的候选人群里）。

防泄漏：
- 特征只读观察窗口内行为/订单，标签只读预测窗口内关键行为与 paid 订单，两窗口互不重叠；
- 同一用户的不同快照在时间上顺序生成，测试集永远使用更晚的快照；
- 不读取 any 未来信息。
"""

from __future__ import annotations

import pandas as pd

from analysis.feature_engineering.config import FeatureConfig
from analysis.feature_engineering.user_features import build_user_features
from analysis.prediction.data import resolve_dataset_range, snapshot_obs_ends

from .config import ChurnConfig

# 每行固定输出列：特征 + 标签 + 快照身份
_OUT_COLS = ("user_id", "obs_end", "label")


def _active_users_in_obs_window(feats: pd.DataFrame) -> pd.Series:
    """候选人群：观察窗口内"活跃"（有任意行为）的用户。"""
    return feats["total_behaviors"] > 0


def _churn_users(
    behaviors: pd.DataFrame,
    orders: pd.DataFrame,
    obs_end: pd.Timestamp,
    label_days: int,
    key_types: tuple[str, ...],
) -> set[str]:
    """预测窗口 (obs_end, obs_end+label_days] 内"仍活跃"的用户（有关键行为或 paid 订单）。

    无关键行为且无购买的用户 => 不在本集合 => churn=1。
    """
    end = obs_end + pd.Timedelta(days=label_days)

    beh = behaviors[["user_id", "behavior_type", "event_time", "event_date"]].copy()
    beh["event_date"] = pd.to_datetime(beh["event_date"], errors="coerce").dt.normalize()
    key = beh[
        (beh["event_date"] > obs_end) & (beh["event_date"] <= end) & (beh["behavior_type"].isin(key_types))
    ]
    still_active = set(key["user_id"])

    ord_ = orders[["user_id", "order_time", "status"]].copy()
    ord_["order_time"] = pd.to_datetime(ord_["order_time"], errors="coerce")
    paid = ord_[(ord_["order_time"] > obs_end) & (ord_["order_time"] <= end) & (ord_["status"] == "paid")]
    still_active |= set(paid["user_id"])
    return still_active


def build_churn_dataset(
    users, behaviors, orders, order_items, items, cfg: ChurnConfig | None = None
) -> pd.DataFrame:
    """构建滚动快照流失样本集（一行/用户/快照，仅观察窗口活跃用户，含 label + obs_end）。

    特征列与 Phase 8 user_features 完全一致，仅额外追加 label 与 obs_end。
    """
    cfg = cfg or ChurnConfig()
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
        active = _active_users_in_obs_window(feats)
        feats = feats[active].copy()
        still = _churn_users(behaviors, orders, obs_end, cfg.label_days, cfg.churn_key_behaviors)
        feats["label"] = (~feats["user_id"].isin(still)).astype(int)
        feats["obs_end"] = obs_end.date().isoformat()
        frames.append(feats)
    out = pd.concat(frames, ignore_index=True)
    return out[list(_OUT_COLS) + [c for c in out.columns if c not in _OUT_COLS]]