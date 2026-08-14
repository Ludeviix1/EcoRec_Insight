"""购买预测模型（Phase 9，开发文档第 49.7 节）。

模型：Logistic Regression（标准化 + 平衡类别权重）+ Random Forest（平衡类别权重）。
评估：Precision / Recall / F1 / ROC-AUC / PR-AUC / Confusion Matrix / Accuracy，
并报告正样本占比；因类别不平衡，绝不只看 Accuracy（开发文档第 49.7 节要求）。

时间切分：按 obs_end 时间先后划分 train / val / test，杜绝未来信息泄漏。
输出：模型 .pkl、metrics.json、feature_importance.json（RF 重要性 + LR 系数）。
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import PREDICTION_FEATURE_COLS, PredictionConfig


def time_split(df: pd.DataFrame, train_ratio: float, val_ratio: float, test_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """按 obs_end 时间先后切分样本集，返回 (train, val, test)。

    保证: 训练/验证/测试在时间上先后衔接，测试集永远使用最晚的快照。
    """
    ends = sorted(df["obs_end"].unique())
    n = len(ends)
    n_test = max(1, round(n * test_ratio))
    n_val = max(0, round(n * val_ratio))
    n_train = n - n_val - n_test
    if n_train < 1:  # 快照过少：优先保证训练集非空
        n_train = 1
        n_val = 0
        n_test = n - n_train
    train_ends = set(ends[:n_train])
    val_ends = set(ends[n_train:n_train + n_val])
    test_ends = set(ends[n_train + n_val:])
    return (
        df[df["obs_end"].isin(train_ends)],
        df[df["obs_end"].isin(val_ends)],
        df[df["obs_end"].isin(test_ends)],
    )


def _safe_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> dict:
    """计算全套评估指标；仅存在单类时 ROC/PR-AUC 返回 None（避免除零/未定义）。"""
    pos = int((y_true == 1).sum())
    total = int(len(y_true))
    metrics = {
        "n_samples": total,
        "n_positive": pos,
        "positive_rate": round(pos / total, 4) if total else 0.0,
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": None,
        "pr_auc": None,
    }
    if len(set(y_true.tolist())) > 1:  # 两类都存在才能算 AUC
        metrics["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
        metrics["pr_auc"] = round(float(average_precision_score(y_true, y_prob)), 4)
    metrics["confusion_matrix"] = confusion_matrix(y_true, y_pred).tolist()
    tn, fp, fn, tp = metrics["confusion_matrix"][0] + metrics["confusion_matrix"][1]
    metrics["precision_from_cm"] = round(tp / (tp + fp), 4) if tp + fp else 0.0
    metrics["recall_from_cm"] = round(tp / (tp + fn), 4) if tp + fn else 0.0
    return metrics


def train_and_evaluate(
    cfg: PredictionConfig, df: pd.DataFrame
) -> tuple[dict, dict, dict]:
    """训练 LR 与 RF，在 train 上拟合、在 val / test 上评估。

    返回: (trained_models, metrics, importance)
    """
    train, val, test = time_split(df, cfg.train_ratio, cfg.val_ratio, cfg.test_ratio)
    X_cols = [c for c in PREDICTION_FEATURE_COLS if c in df.columns]
    X_train = train[X_cols].fillna(0.0).to_numpy()
    y_train = train["label"].to_numpy()
    X_val = val[X_cols].fillna(0.0).to_numpy()
    y_val = val["label"].to_numpy()
    X_test = test[X_cols].fillna(0.0).to_numpy()
    y_test = test["label"].to_numpy()

    lr = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            max_iter=cfg.lr_max_iter,
            class_weight="balanced",
            random_state=cfg.random_state,
        ),
    )
    rf = RandomForestClassifier(
        n_estimators=cfg.rf_n_estimators,
        max_depth=cfg.rf_max_depth,
        class_weight="balanced",
        random_state=cfg.random_state,
        n_jobs=-1,
    )

    lr.fit(X_train, y_train)
    rf.fit(X_train, y_train)

    models = {"logistic_regression": lr, "random_forest": rf}
    metrics: dict[str, dict] = {}
    for name, model in models.items():
        prob = model.predict_proba(X_val)[:, 1]
        metrics[name] = {
            "val": _safe_metrics(y_val, (prob >= 0.5).astype(int), prob),
            "test": _safe_metrics(y_test, (model.predict_proba(X_test)[:, 1] >= 0.5).astype(int), model.predict_proba(X_test)[:, 1]),
        }

    importance = _feature_importance(models, X_cols)
    return models, metrics, importance


def _feature_importance(models: dict, X_cols: list[str]) -> dict:
    """输出 RF 特征重要性（归一化）+ LR 标准化系数的绝对值排序。"""
    lr = models["logistic_regression"]
    rf = models["random_forest"]
    rf_imp = rf.feature_importances_
    lr_coef = (
        lr.named_steps["logisticregression"].coef_[0]
        if hasattr(lr, "named_steps")
        else lr.coef_[0]
    )
    lr_abs = np.abs(lr_coef)
    return {
        "random_forest_top20": [
            {"feature": f, "importance": round(float(v), 4)}
            for f, v in sorted(zip(X_cols, rf_imp), key=lambda kv: -kv[1])[:20]
        ],
        "logistic_regression_coeff_top20": [
            {"feature": f, "coef": round(float(c), 4), "abs_coef": round(float(abs(c)), 4)}
            for f, c in sorted(zip(X_cols, lr_coef), key=lambda kv: -abs(kv[1]))[:20]
        ],
    }


def save_model(model, path: Path | str) -> None:
    """保存训练好的模型（.pkl）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, p)


def write_json(path: Path | str, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")