"""模型产物仓库：读取购买/流失预测与推荐评估的离线产物。

- 购买预测：data/prediction/（prediction_meta / metrics / feature_importance / snapshot_dataset / 模型 pkl）
- 流失预测：data/churn/（churn_meta / metrics / feature_importance / churn_predictions）
- 推荐评估：data/recommendation/（evaluation_summary / algo_comparison / weight_experiment）

API 只做"离线训练 → 加载模型 → 服务"，禁止请求时重新训练（开发文档第 46 节）。
"""

from __future__ import annotations

import logging
from functools import lru_cache

import joblib
import pandas as pd

from analysis.prediction.config import PREDICTION_FEATURE_COLS

from ..core.exceptions import NotFoundError
from .base import CHURN_DIR, PREDICTION_DIR, RECOMMENDATION_DIR, read_json

logger = logging.getLogger("api.model_repo")


# ---- 购买预测 ----
def purchase_meta() -> dict:
    return read_json(PREDICTION_DIR, "prediction_meta")


def purchase_metrics() -> dict:
    return read_json(PREDICTION_DIR, "metrics")


def purchase_importance() -> dict:
    return read_json(PREDICTION_DIR, "feature_importance")


@lru_cache(maxsize=1)
def snapshot_dataset_df() -> pd.DataFrame:
    p = PREDICTION_DIR / "snapshot_dataset.csv"
    if not p.exists():
        raise NotFoundError(message="购买预测样本集不存在，请先运行 scripts/run_prediction.py")
    return pd.read_csv(p, dtype={"user_id": str})


@lru_cache(maxsize=1)
def _lr_model():
    p = PREDICTION_DIR / "model_logistic_regression.pkl"
    if not p.exists():
        return None
    return joblib.load(p)


def user_purchase_prediction(user_id: str) -> dict | None:
    """用保存的 LR 模型对用户最近一次快照做购买概率预测（不重新训练）。"""
    df = snapshot_dataset_df()
    if df is None or len(df) == 0:
        return None
    sub = df[df["user_id"] == str(user_id)]
    if len(sub) == 0:
        return None
    latest_end = sub["obs_end"].max()
    row = sub[sub["obs_end"] == latest_end].iloc[0]
    model = _lr_model()
    if model is None:
        return None
    feat_cols = [c for c in PREDICTION_FEATURE_COLS if c in df.columns]
    X = row[feat_cols].to_numpy().reshape(1, -1).astype(float)
    prob = float(model.predict_proba(X)[0, 1])
    return {
        "user_id": str(user_id),
        "purchase_probability": round(prob, 4),
        "obs_end": str(latest_end),
        "label_days": int(purchase_meta().get("time_windows", {}).get("label_days", 7)),
        "model": "logistic_regression",
    }


# ---- 流失预测 ----
def churn_meta() -> dict:
    return read_json(CHURN_DIR, "churn_meta")


def churn_metrics() -> dict:
    return read_json(CHURN_DIR, "metrics")


def churn_importance() -> dict:
    return read_json(CHURN_DIR, "feature_importance")


@lru_cache(maxsize=1)
def churn_predictions_df() -> pd.DataFrame:
    p = CHURN_DIR / "churn_predictions.csv"
    if not p.exists():
        raise NotFoundError(message="流失预测结果不存在，请先运行 scripts/run_churn.py")
    return pd.read_csv(p, dtype={"user_id": str})


def user_churn_prediction(user_id: str) -> dict | None:
    df = churn_predictions_df()
    if df is None or len(df) == 0:
        return None
    sub = df[df["user_id"] == str(user_id)]
    if len(sub) == 0:
        return None
    r = sub.iloc[0]
    return {
        "user_id": str(user_id),
        "churn_probability": round(float(r["churn_probability"]), 4),
        "risk_level": str(r["risk_level"]),
        "obs_end": str(r.get("obs_end", "")),
    }


# ---- 推荐评估 ----
def evaluation_summary() -> dict:
    """5 算法离线评估结果：优先 evaluation_summary.json，其次 algo_comparison.json。"""
    for name in ("evaluation_summary", "algo_comparison"):
        p = RECOMMENDATION_DIR / f"{name}.json"
        if p.exists():
            return read_json(RECOMMENDATION_DIR, name)
    raise NotFoundError(message="推荐评估结果不存在，请先运行 scripts/run_evaluation.py")


def weight_experiment() -> dict:
    return read_json(RECOMMENDATION_DIR, "weight_experiment")