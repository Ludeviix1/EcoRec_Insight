"""Phase 10 流失预测测试（开发文档第 49.8 节）。

覆盖：
- 流失标签定义：观察窗口活跃 + 未来 30 天无关键行为且无购买 => churn=1；
- 候选人群：观察窗口不活跃的用户不进入样本集；
- 防泄漏：特征只读观察窗口，标签只读预测窗口，两窗口不重叠；
- 快照：obs_end 序列时间升序；
- 时间切分：train/val/test 按时间先后切分，测试集使用最晚快照（非随机）；
- 风险等级：user_id / churn_probability / risk_level 输出与阈值逻辑；
- end-to-end：生成 -> ETL -> 流失预测 -> 模型/指标/预测/元数据落盘。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.churn.config import ChurnConfig, load_churn_config
from analysis.churn.data import build_churn_dataset
from analysis.churn.run import _risk_level, _predict_on_latest_snapshot, run_churn
from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl
from analysis.prediction.config import PREDICTION_FEATURE_COLS
from analysis.prediction.model import time_split, train_and_evaluate

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


# ---------------------------------------------------------------------
# 构造手工测试数据（观察窗口 2026-08-02~08-31，预测窗口 (08-31, 09-07]）
# ---------------------------------------------------------------------
OBS_END = "2026-08-31"
_CFG = ChurnConfig(observation_days=30, label_days=7, snapshot_ends=(OBS_END,),
                   train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)


def _behaviors() -> pd.DataFrame:
    return pd.DataFrame({
        "behavior_id": ["B1", "B2", "B3", "B4", "B5"],
        "user_id": ["U1", "U2", "U3", "U4", "U5"],
        "item_id": ["I1", "I1", "I1", "I1", "I1"],
        "behavior_type": ["pv", "click", "pv", "pv", "pv"],
        "event_time": ["2026-08-05 10:00:00", "2026-08-10 10:00:00",
                       "2026-08-25 10:00:00", "2026-08-30 10:00:00", "2026-07-01 10:00:00"],
        "event_date": ["2026-08-05", "2026-08-10", "2026-08-25", "2026-08-30", "2026-07-01"],
        "event_hour": [10, 10, 10, 10, 10],
        "device_type": ["pc", "mobile", "mobile", "pc", "pc"],
        "channel": ["organic", "organic", "search", "campaign", "organic"],
    })


def _behaviors_future_key() -> pd.DataFrame:
    """在预测窗口内有关键 behavior（buy/collect/cart）的补充行为。"""
    return pd.concat([
        _behaviors(),
        pd.DataFrame({
            "behavior_id": ["B6"],
            "user_id": ["U2"],
            "item_id": ["I1"],
            "behavior_type": ["buy"],
            "event_time": ["2026-09-05 10:00:00"],
            "event_date": ["2026-09-05"],
            "event_hour": [10],
            "device_type": ["mobile"],
            "channel": ["organic"],
        }),
    ], ignore_index=True)


def _users() -> pd.DataFrame:
    return pd.DataFrame({
        "user_id": ["U1", "U2", "U3", "U4", "U5"],
        "age": [25.0, 30.0, 35.0, 40.0, 45.0],
        "gender": ["M", "F", "M", "F", "M"],
        "city": ["北京", "上海", "广州", "深圳", "杭州"],
        "register_time": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
        "created_at": ["2026-01-01"] * 5,
        "updated_at": ["2026-01-01"] * 5,
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
    """O1: 观察窗口内购买（不影响 churn）；订单在预测窗口内 => 未流失。"""
    return pd.DataFrame({
        "order_id": ["O1", "O2"],
        "user_id": ["U3", "U4"],
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
# 一、流失标签定义与候选人群
# ---------------------------------------------------------------------
def test_churn_label_definition():
    """观察窗口活跃 + 未来 30 天无关键行为且无购买 => churn=1。"""
    out = build_churn_dataset(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    labels = dict(zip(out["user_id"], out["label"]))
    assert labels["U1"] == 1      # 观察窗口活跃，未来无任何动作 => 流失
    assert labels["U2"] == 1      # 观察窗口活跃，未来只有 pv/click（非关键行为）=> 流失
    assert labels["U3"] == 1      # 观察窗口活跃，预测窗口无动作 => 流失（O1 在观察窗口内不算）
    assert labels["U4"] == 0      # 预测窗口内 paid 订单（09-05）=> 未流失
    assert "label" in out.columns and "obs_end" in out.columns


def test_churn_label_key_behavior_counts():
    """未来窗口有关键行为（buy/collect/cart）视为未流失。"""
    out = build_churn_dataset(_users(), _behaviors_future_key(), _orders(), _order_items(), _items(), _CFG)
    labels = dict(zip(out["user_id"], out["label"]))
    assert labels["U2"] == 0      # 预测窗口内有 buy 行为 => 未流失


def test_inactive_users_excluded_from_candidate_pool():
    """观察窗口不活跃的用户（U5）不应进入流失样本集。"""
    out = build_churn_dataset(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    assert "U5" not in set(out["user_id"])     # U5 观察窗口最后一个行为在 07-01，不在窗口内


def test_churn_dataset_has_features_and_no_future_leakage():
    out = build_churn_dataset(_users(), _behaviors_future_key(), _orders(), _order_items(), _items(), _CFG)
    assert set(PREDICTION_FEATURE_COLS).issubset(set(out.columns))
    assert set(out["obs_end"]) == {"2026-08-31"}
    # U2 的 buy 行为在 09-05（预测窗口），不得计入观察窗口特征
    assert out.loc[out["user_id"] == "U2", "n_buy"].iloc[0] == 0
    # U3 的 O1 在观察窗口内 => 特征 n_buy/purchase 计入，但 label 只看预测窗口
    assert out.loc[out["user_id"] == "U3", "paid_order_count"].iloc[0] == 1


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


# ---------------------------------------------------------------------
# 三、模型训练与评估
# ---------------------------------------------------------------------
def _synthetic_churn_dataset() -> pd.DataFrame:
    """手工构造多快照流失样本集（3 快照 × 6 用户，正负样本混合）。"""
    rows = []
    for i, obs_end in enumerate(["2026-08-01", "2026-08-08", "2026-08-15"]):
        for u in range(6):
            churned = (u % 3 == 0) or (u == 5)   # 用户0/3/5 未来无动作 => 流失
            rows.append({
                "user_id": f"U{u}",
                "obs_end": obs_end,
                "label": 1 if (i <= 1 and churned) else 0,
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
                "paid_order_count": 0, "paid_gmv": 0.0,
                "avg_order_amount": 0.0, "max_order_amount": 0.0,
                "purchased_items": 0, "purchased_categories": 0,
                "purchase_days": 0, "has_purchase": 0,
            })
    return pd.DataFrame(rows)


def test_train_evaluate_metrics_cover_required():
    df = _synthetic_churn_dataset()
    models, metrics, importance = train_and_evaluate(_CFG, df)
    for name in ("logistic_regression", "random_forest"):
        assert name in models and name in metrics
        for split in ("val", "test"):
            m = metrics[name][split]
            for key in ("precision", "recall", "roc_auc", "pr_auc", "confusion_matrix", "positive_rate"):
                assert key in m, f"{name}.{split}.{key} 缺失"
    assert "random_forest_top20" in importance and "logistic_regression_coeff_top20" in importance


# ---------------------------------------------------------------------
# 四、风险等级
# ---------------------------------------------------------------------
def test_risk_level_thresholds():
    cfg = ChurnConfig()
    assert _risk_level(0.1, cfg) == "low"
    assert _risk_level(0.3, cfg) == "medium"   # p == low_threshold => medium
    assert _risk_level(0.5, cfg) == "medium"
    assert _risk_level(0.7, cfg) == "medium"   # p == high_threshold => medium
    assert _risk_level(0.8, cfg) == "high"


# ---------------------------------------------------------------------
# 五、end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def churn_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase10")
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

    ccfg = load_churn_config(
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        output_dir=str(root / "churn"),
        observation_days=30,
        label_days=7,
        snapshot_step=7,
        rf_n_estimators=20,
    )
    run_churn(ccfg, log=False)
    return root / "churn"


def test_run_churn_outputs(churn_dir):
    assert (churn_dir / "churn_dataset.csv").exists()
    for name in ("logistic_regression", "random_forest"):
        assert (churn_dir / f"model_{name}.pkl").exists()

    meta = json.loads((churn_dir / "churn_meta.json").read_text(encoding="utf-8"))
    assert meta["task"] == "churn_prediction"
    assert meta["churn_definition"]            # 流失定义必须说明
    assert meta["time_windows"]["observation_window"]
    assert meta["time_windows"]["prediction_window"]
    assert meta["leakage_guard"]
    assert meta["data_split"]["n_snapshots"] >= 3
    assert meta["risk_level"]["high"] >= 0
    assert set(meta["results"]) == {"logistic_regression", "random_forest"}

    metrics = json.loads((churn_dir / "metrics.json").read_text(encoding="utf-8"))
    for name in ("logistic_regression", "random_forest"):
        assert "val" in metrics[name] and "test" in metrics[name]
        assert metrics[name]["test"]["confusion_matrix"]

    importance = json.loads((churn_dir / "feature_importance.json").read_text(encoding="utf-8"))
    assert len(importance["random_forest_top20"]) > 0
    assert len(importance["logistic_regression_coeff_top20"]) > 0


def test_churn_predictions_file(churn_dir):
    preds = pd.read_csv(churn_dir / "churn_predictions.csv", encoding="utf-8-sig")
    assert set(preds.columns) >= {"user_id", "churn_probability", "risk_level"}
    assert preds["churn_probability"].between(0, 1).all()
    assert set(preds["risk_level"]).issubset({"low", "medium", "high"})
    assert preds.shape[0] >= 1


def test_meta_time_split_chronological(churn_dir):
    meta = json.loads((churn_dir / "churn_meta.json").read_text(encoding="utf-8"))
    assert meta["data_split"]["rule"] == "按 obs_end 时间先后切分，非随机切分"
    snapshot = pd.read_csv(churn_dir / "churn_dataset.csv", encoding="utf-8-sig")
    assert snapshot["obs_end"].is_monotonic_increasing