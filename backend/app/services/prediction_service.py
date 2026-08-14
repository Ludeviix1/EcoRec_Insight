"""预测模型服务：购买预测 / 流失预测 / 模型评估汇总。

口径（开发文档第 49.7/49.8 节）：观察窗口生成特征，预测窗口生成标签，
时间切分防泄漏，类别不平衡不以 Accuracy 为准。API 只加载离线模型，不重训。
"""

from __future__ import annotations

import logging

from ..repositories import analysis_repo, model_repo

logger = logging.getLogger("api.prediction_service")


def _top_importance(importance: dict, top: int = 20) -> list[dict]:
    rows = importance.get("importance") or importance.get("feature_importance") or []
    return rows[:top]


def purchase() -> dict:
    meta = model_repo.purchase_meta()
    metrics = model_repo.purchase_metrics()
    importance = model_repo.purchase_importance()
    best = _best_model(metrics)
    return {
        "task": meta.get("task"),
        "dataset_version": meta.get("dataset_version"),
        "prediction_version": meta.get("prediction_version"),
        "description": meta.get("description"),
        "time_windows": meta.get("time_windows"),
        "leakage_guard": meta.get("leakage_guard"),
        "data_split": meta.get("data_split"),
        "features": meta.get("features"),
        "models": meta.get("models"),
        "config": meta.get("config"),
        "run_at": meta.get("run_at"),
        "metrics": metrics,
        "best_model": best,
        "feature_importance": _top_importance(importance),
    }


def churn(limit: int = 50) -> dict:
    meta = model_repo.churn_meta()
    metrics = model_repo.churn_metrics()
    importance = model_repo.churn_importance()
    best = _best_model(metrics)
    preds = model_repo.churn_predictions_df()
    preds = preds.sort_values("churn_probability", ascending=False).head(limit)
    return {
        "task": meta.get("task"),
        "dataset_version": meta.get("dataset_version"),
        "churn_version": meta.get("churn_version"),
        "description": meta.get("description"),
        "churn_definition": meta.get("churn_definition"),
        "time_windows": meta.get("time_windows"),
        "leakage_guard": meta.get("leakage_guard"),
        "data_split": meta.get("data_split"),
        "risk_level": meta.get("risk_level"),
        "config": meta.get("config"),
        "run_at": meta.get("run_at"),
        "metrics": metrics,
        "best_model": best,
        "feature_importance": _top_importance(importance),
        "predictions": preds.to_dict("records"),
    }


def metrics() -> dict:
    """模型评估汇总：购买 / 流失（test 集）+ 推荐评估 + 权重实验。"""
    pm = _model_test_scores(model_repo.purchase_metrics())
    cm = _model_test_scores(model_repo.churn_metrics())
    ev = model_repo.evaluation_summary()
    rec = ev.get("results") or {}
    rec_rows = [
        {
            "algorithm": alg,
            "precision@k": m.get("precision@k"),
            "recall@k": m.get("recall@k"),
            "f1@k": m.get("f1@k"),
            "hit_rate@k": m.get("hit_rate@k"),
            "ndcg@k": m.get("ndcg@k"),
            "coverage@k": m.get("coverage@k"),
        }
        for alg, m in sorted(rec.items())
    ]
    wexp = {}
    try:
        wexp = model_repo.weight_experiment()
    except Exception:
        pass
    return {
        "purchase": pm,
        "churn": cm,
        "recommendation": {
            "k": ev.get("k"),
            "test_ratio": ev.get("test_ratio"),
            "baseline": ev.get("baseline"),
            "conclusion": ev.get("conclusion"),
            "algorithms": rec_rows,
        },
        "weight_experiment": {
            "best_experiment": wexp.get("best_experiment"),
            "best_weights": wexp.get("best_weights"),
            "selection_criterion": wexp.get("selection_criterion"),
            "variants": wexp.get("variants"),
        },
    }


def user_churn(user_id: str) -> dict | None:
    return model_repo.user_churn_prediction(user_id)


def user_purchase(user_id: str) -> dict | None:
    return model_repo.user_purchase_prediction(user_id)


def _model_test_scores(metrics: dict) -> dict:
    out = {}
    for name, m in (metrics or {}).items():
        test = (m or {}).get("test") or {}
        out[name] = {
            "n_samples": test.get("n_samples"),
            "positive_rate": test.get("positive_rate"),
            "accuracy": test.get("accuracy"),
            "precision": test.get("precision"),
            "recall": test.get("recall"),
            "f1": test.get("f1"),
            "roc_auc": test.get("roc_auc"),
            "pr_auc": test.get("pr_auc"),
            "confusion_matrix": test.get("confusion_matrix"),
        }
    return out


def _best_model(metrics: dict) -> dict | None:
    """依据测试集 PR-AUC / F1 选取更优模型（诚实，不主观拍脑袋）。"""
    best_name, best_key = None, -1.0
    for name, m in (metrics or {}).items():
        test = (m or {}).get("test") or {}
        score = test.get("pr_auc")
        if score is None:
            score = test.get("f1", 0.0)
        if score is not None and float(score) > best_key:
            best_key, best_name = float(score), name
    if best_name is None:
        return None
    return {"model": best_name, "selection": "按测试集 PR-AUC（缺省取 F1）更高者", "test": (metrics or {}).get(best_name, {}).get("test")}