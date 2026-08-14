"""Phase 9 购买预测测试（开发文档第 49.7 节）。

覆盖：
- 样本集：观察窗口特征 + 未来 7 天购买 label，两窗口不重叠（防泄漏）；
- 快照：obs_end 序列时间升序、窗口完全落在数据范围内；
- 时间切分：train/val/test 按时间先后切分，测试集使用最晚快照（非随机）；
- 模型：LR / RF 训练与评估输出全套指标（Precision/Recall/F1/ROC-AUC/PR-AUC/混淆矩阵）；
- 类别不平衡：报告 positive_rate，不以 Accuracy 为准；
- 特征重要性：RF 归一化重要性 + LR 标准化系数绝对值排序；
- 可复现：同配置两次运行完全一致；
- end-to-end：生成 -> ETL -> 购买预测 -> 模型/指标/重要性/meta 落盘。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl
from analysis.feature_engineering.base import load_processed
from analysis.prediction.config import PREDICTION_FEATURE_COLS, PredictionConfig, load_prediction_config
from analysis.prediction.data import build_snapshot_dataset, resolve_dataset_range, snapshot_obs_ends
from analysis.prediction.model import time_split, train_and_evaluate
from analysis.prediction.run import run_prediction

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


# ---------------------------------------------------------------------
# 构造手工测试数据（观察窗口 2026-08-02~08-31，预测窗口 (08-31, 09-07]）
# ---------------------------------------------------------------------
OBS_END = "2026-08-31"
_CFG = PredictionConfig(observation_days=30, label_days=7, snapshot_ends=(OBS_END,), train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)


def _behaviors() -> pd.DataFrame:
    return pd.DataFrame({
        "behavior_id": ["B1", "B2", "B3", "B4"],
        "user_id": ["U1", "U1", "U2", "U3"],
        "item_id": ["I1", "I1", "I1", "I1"],
        "behavior_type": ["pv", "click", "pv", "pv"],
        "event_time": ["2026-08-05 10:00:00", "2026-08-05 10:05:00",
                       "2026-08-10 10:00:00", "2026-08-25 10:00:00"],
        "event_date": ["2026-08-05", "2026-08-05", "2026-08-10", "2026-08-25"],
        "event_hour": [10, 10, 10, 10],
        "device_type": ["pc", "mobile", "mobile", "pc"],
        "channel": ["organic", "organic", "search", "campaign"],
    })


def _users() -> pd.DataFrame:
    return pd.DataFrame({
        "user_id": ["U1", "U2", "U3"],
        "age": [25.0, 30.0, 35.0],
        "gender": ["M", "F", "M"],
        "city": ["北京", "上海", "广州"],
        "register_time": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "created_at": ["2026-01-01"] * 3,
        "updated_at": ["2026-01-01"] * 3,
    })


def _items() -> pd.DataFrame:
    return pd.DataFrame({
        "item_id": ["I1", "I2"],
        "item_name": ["手机A", "手机B"],
        "category_id": ["C01", "C02"],
        "brand": ["华为", "小米"],
        "price": [3999.0, 2999.0],
        "stock": [100.0, 200.0],
        "status": [1, 1],
        "created_at": ["2026-01-01", "2026-01-01"],
    })


def _orders() -> pd.DataFrame:
    # O1: 观察窗口内购买（不计入 label）; O2: 预测窗口内购买（label=1）
    return pd.DataFrame({
        "order_id": ["O1", "O2"],
        "user_id": ["U1", "U2"],
        "order_time": ["2026-08-20 10:00:00", "2026-09-05 10:00:00"],
        "total_amount": [100.0, 999.0],
        "status": ["paid", "paid"],
        "payment_method": ["balance", "balance"],
    })


def _order_items() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1", "O2"],
        "item_id": ["I1", "I1"],
        "quantity": [1, 1],
        "unit_price": [100.0, 999.0],
        "amount": [100.0, 999.0],
    })


# ---------------------------------------------------------------------
# 一、样本集与防泄漏
# ---------------------------------------------------------------------
def test_snapshot_label_window_no_overlap():
    """label 只取预测窗口 (obs_end, obs_end+7] 内的 paid 订单，观察窗口内购买不算。"""
    out = build_snapshot_dataset(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    labels = dict(zip(out["user_id"], out["label"]))
    assert labels["U1"] == 0      # 观察窗口内 08-20 购买 -> 不计入 label
    assert labels["U2"] == 1      # 预测窗口内 09-05 购买 -> label=1
    assert labels["U3"] == 0      # 无购买
    assert "label" in out.columns and "obs_end" in out.columns


def test_snapshot_dataset_has_features_and_no_future_leakage():
    out = build_snapshot_dataset(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    assert set(PREDICTION_FEATURE_COLS).issubset(set(out.columns))
    assert set(out["obs_end"]) == {"2026-08-31"}
    assert out["total_behaviors"].sum() == 4       # 仅观察窗口内行为
    assert out["paid_order_count"].sum() == 1      # 仅观察窗口内 O1 计入特征；O2 是未来不计入


def test_resolve_dataset_range_bounds():
    """数据跨度 06-02~08-31 时，可容纳 30 天观察窗口 + 7 天预测窗口。"""
    dates = pd.date_range("2026-06-02", "2026-08-31", freq="D")
    wide = pd.DataFrame({
        "behavior_id": [f"B{i}" for i in range(len(dates))],
        "user_id": "U1",
        "item_id": "I1",
        "behavior_type": "pv",
        "event_time": [str(d + pd.Timedelta(hours=10)) for d in dates],
        "event_date": [d.date().isoformat() for d in dates],
        "event_hour": [10] * len(dates),
        "device_type": "pc",
        "channel": "organic",
    })
    earliest, latest = resolve_dataset_range(_CFG, wide)
    assert str(earliest.date()) == "2026-07-01"     # 06-02 + 29 天 => 观察窗口落在数据内
    assert str(latest.date()) == "2026-08-24"       # 08-31 - 7 天 => 预测窗口落在数据内


def test_resolve_dataset_range_too_short_raises():
    """数据跨度不足 30+7 天时明确报错（避免静默生成全 0 假样本）。"""
    short = _behaviors()  # 仅 08-05~08-25
    with pytest.raises(ValueError):
        resolve_dataset_range(_CFG, short)


def test_snapshot_obs_ends_ascending():
    behaviors = _behaviors()
    ends = snapshot_obs_ends(_CFG, behaviors)
    assert ends == sorted(ends)


# ---------------------------------------------------------------------
# 二、时间切分
# ---------------------------------------------------------------------
def test_time_split_by_time_not_random():
    ends = [f"2026-08-0{i}" for i in range(1, 10)]
    df = pd.DataFrame({"obs_end": ends * 2, "label": [0] * 18, "user_id": ["x"] * 18})
    train, val, test = time_split(df, 0.6, 0.2, 0.2)
    assert train["obs_end"].max() <= val["obs_end"].min() if len(val) else True
    assert val["obs_end"].max() <= test["obs_end"].min() if len(val) else True
    assert test["obs_end"].max() == "2026-08-09"    # 最晚快照进测试集
    assert train["obs_end"].nunique() == 5


def test_time_split_requires_test_nonempty():
    df = pd.DataFrame({"obs_end": ["2026-08-01"] * 3 + ["2026-08-02"] * 3,
                       "label": [0] * 6, "user_id": ["x"] * 6})
    train, val, test = time_split(df, 0.6, 0.2, 0.2)
    assert len(test) >= 1 and len(train) >= 1
    assert set(train["obs_end"]) <= set(df["obs_end"].unique())


# ---------------------------------------------------------------------
# 三、模型训练与评估
# ---------------------------------------------------------------------
def _synthetic_dataset() -> pd.DataFrame:
    """手工构造多快照样本集（3 快照 × 6 用户，正负样本混合），供模型测试使用。"""
    rows = []
    for i, obs_end in enumerate(["2026-08-01", "2026-08-08", "2026-08-15"]):
        for u in range(6):
            buyer = (u % 3 == 0) or (u == 5)   # 用户0/3/5 在预测窗口购买 => label=1
            rows.append({
                "user_id": f"U{u}",
                "obs_end": obs_end,
                "label": 1 if (i <= 1 and buyer) else 0,
                "age": 20.0 + u * 3,
                "gender_m": 1, "gender_f": 0,
                "register_days": 100 + u, "is_new_in_window": 0,
                "total_behaviors": 10 + i + u, "n_pv": 8 + i, "n_click": 2,
                "n_collect": 1, "n_cart": 1, "n_buy": 0,
                "behavior_buy_ratio": 0.0, "n_active_days": 3 + u, "active_day_ratio": 0.2,
                "behaviors_per_active_day": 3.0, "avg_behaviors_per_day": 0.5,
                "n_sessions": 2, "behaviors_per_session": 4.0,
                "recency_days": 5, "first_activity_offset_days": 10,
                "n_distinct_items": 4 + u, "n_distinct_categories": 2,
                "n_channels": 2, "n_devices": 2,
                "click_rate": 0.25, "collect_rate": 0.1, "cart_rate": 0.1, "buy_rate": 0.0,
                "paid_order_count": 1 if buyer else 0, "paid_gmv": 299.0 if buyer else 0.0,
                "avg_order_amount": 299.0 if buyer else 0.0, "max_order_amount": 299.0 if buyer else 0.0,
                "purchased_items": 1 if buyer else 0, "purchased_categories": 1 if buyer else 0,
                "purchase_days": 1 if buyer else 0, "has_purchase": 1 if buyer else 0,
            })
    return pd.DataFrame(rows)


def test_train_evaluate_metrics_cover_required():
    df = _synthetic_dataset()
    models, metrics, importance = train_and_evaluate(_CFG, df)
    for name in ("logistic_regression", "random_forest"):
        assert name in models and name in metrics
        for split in ("val", "test"):
            m = metrics[name][split]
            for key in ("precision", "recall", "roc_auc", "pr_auc", "confusion_matrix", "positive_rate"):
                assert key in m, f"{name}.{split}.{key} 缺失"
            assert m["positive_rate"] <= 1.0
    assert "random_forest_top20" in importance and "logistic_regression_coeff_top20" in importance


def test_class_imbalance_reported_not_only_accuracy():
    df = _synthetic_dataset()
    models, metrics, importance = train_and_evaluate(_CFG, df)
    for name in ("logistic_regression", "random_forest"):
        assert "positive_rate" in metrics[name]["test"]
        # 评估口径不是单一的 accuracy
        assert set(metrics[name]["test"].keys()) >= {"precision", "recall", "roc_auc", "pr_auc"}


# ---------------------------------------------------------------------
# 四、可复现
# ---------------------------------------------------------------------
def test_reproducible():
    a = train_and_evaluate(_CFG, _synthetic_dataset())
    b = train_and_evaluate(_CFG, _synthetic_dataset())
    assert a[1] == b[1]            # 指标一致
    assert a[2] == b[2]            # 特征重要性一致


# ---------------------------------------------------------------------
# 五、end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def prediction_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase9")
    raw = root / "raw"
    gen_cfg = load_config(output_dir=str(raw), **TEST_GEN)
    run_generation(gen_cfg, log=False)

    etl_cfg = load_etl_config(
        raw_dir=str(raw),
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        mysql=False,
        chunk_size=1000,
    )
    run_etl(etl_cfg, log=False)

    pcfg = load_prediction_config(
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        output_dir=str(root / "prediction"),
        observation_days=30,
        label_days=7,
        snapshot_step=7,
        rf_n_estimators=20,
    )
    run_prediction(pcfg, log=False)
    return root / "prediction"


def test_run_prediction_outputs(prediction_dir):
    assert (prediction_dir / "snapshot_dataset.csv").exists()
    for name in ("logistic_regression", "random_forest"):
        assert (prediction_dir / f"model_{name}.pkl").exists()

    meta = json.loads((prediction_dir / "prediction_meta.json").read_text(encoding="utf-8"))
    assert meta["task"] == "purchase_prediction"
    assert meta["time_windows"]["observation_days"] == 30
    assert meta["time_windows"]["label_days"] == 7
    assert meta["leakage_guard"]
    assert meta["data_split"]["n_snapshots"] >= 3
    assert meta["data_split"]["test"]["rows"] >= 1
    assert set(meta["results"]) == {"logistic_regression", "random_forest"}

    metrics = json.loads((prediction_dir / "metrics.json").read_text(encoding="utf-8"))
    for name in ("logistic_regression", "random_forest"):
        assert "val" in metrics[name] and "test" in metrics[name]
        assert "pr_auc" in metrics[name]["test"] or metrics[name]["test"]["n_positive"] == 0
        assert metrics[name]["test"]["confusion_matrix"]

    importance = json.loads((prediction_dir / "feature_importance.json").read_text(encoding="utf-8"))
    assert len(importance["random_forest_top20"]) > 0
    assert len(importance["logistic_regression_coeff_top20"]) > 0


def test_prediction_meta_time_split_chronological(prediction_dir):
    meta = json.loads((prediction_dir / "prediction_meta.json").read_text(encoding="utf-8"))
    assert meta["data_split"]["rule"] == "按 obs_end 时间先后切分，非随机切分"
    snapshot = pd.read_csv(prediction_dir / "snapshot_dataset.csv", encoding="utf-8-sig")
    assert snapshot["obs_end"].is_monotonic_increasing