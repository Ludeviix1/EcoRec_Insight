"""流失预测全量入口（Phase 10，开发文档第 49.8 节）。

流程：
    data/processed 六张清洗 CSV
        ↓ 滚动快照构建流失样本集（观察窗口特征 + 未来 30 天无关键行为/购买 => churn=1）
    time split -> LR / RF 训练与评估
        ↓
    data/churn/ 模型 .pkl + metrics.json + feature_importance.json + churn_meta.json
    + churn_predictions.csv（user_id / churn_probability / risk_level，取最优模型的预测）

输出（开发文档第 49.8 节）：
    user_id / churn_probability / risk_level（low/medium/high）
必须说明（写入 churn_meta.json）：
    观察窗口 / 预测窗口 / 流失定义
"""

from __future__ import annotations

import argparse
import json
import logging
import time

import numpy as np
import pandas as pd

from analysis.etl.pipeline import run_etl  # noqa: F401  # 保持与其它 Phase 一致的导入面

from .config import ChurnConfig, load_churn_config
from .data import build_churn_dataset
from .model import save_model, time_split, train_and_evaluate, write_json

logger = logging.getLogger("analysis.churn")

_MODEL_NAMES = ("logistic_regression", "random_forest")


def _dataset_version(cfg: ChurnConfig) -> str:
    p = cfg.interim_dir / "etl_meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("dataset_version", "unknown")
        except Exception:
            return "unknown"
    return "unknown"


def _risk_level(p: float, cfg: ChurnConfig) -> str:
    if p < cfg.risk_low_threshold:
        return "low"
    if p > cfg.risk_high_threshold:
        return "high"
    return "medium"


def _predict_on_latest_snapshot(
    models: dict, dataset: pd.DataFrame, cfg: ChurnConfig
) -> pd.DataFrame:
    """用 LR（可解释、确定性）对最晚快照的候选人群打分。

    返回 DataFrame: user_id / churn_probability / risk_level。
    """
    from analysis.prediction.config import PREDICTION_FEATURE_COLS

    latest_end = dataset["obs_end"].max()
    snap = dataset[dataset["obs_end"] == latest_end].copy()
    X_last = snap[[c for c in PREDICTION_FEATURE_COLS if c in snap.columns]].fillna(0.0).to_numpy()

    model = models.get("logistic_regression")
    if model is None:
        model = models[list(models.keys())[0]]

    prob = model.predict_proba(X_last)[:, 1]
    out = pd.DataFrame({
        "user_id": snap["user_id"].to_numpy(),
        "churn_probability": np.round(prob, 4),
    })
    out["risk_level"] = [_risk_level(float(p), cfg) for p in prob]
    out["obs_end"] = latest_end
    return out.sort_values("churn_probability", ascending=False).reset_index(drop=True)


def run_churn(cfg: ChurnConfig | None = None, *, log: bool = True) -> dict:
    """执行流失预测，返回运行记录 dict（已落盘 data/churn/churn_meta.json）。"""
    cfg = cfg or load_churn_config()
    if log:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    t0 = time.perf_counter()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    from analysis.feature_engineering.base import load_processed

    users = load_processed(cfg.processed_dir, "users")
    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")
    logger.info("加载 processed 完成 | users=%d behaviors=%d orders=%d",
                len(users), len(behaviors), len(orders))

    dataset = build_churn_dataset(users, behaviors, orders, order_items, items, cfg)
    dataset_path = cfg.output_dir / "churn_dataset.csv"
    dataset.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    logger.info("流失样本集写入 %s (%d 行, 流失率=%.2f%%)",
                dataset_path.name, len(dataset),
                100.0 * dataset["label"].mean() if len(dataset) else 0.0)

    train, val, test = time_split(dataset, cfg.train_ratio, cfg.val_ratio, cfg.test_ratio)
    models, metrics, importance = train_and_evaluate(cfg, dataset)

    model_paths: dict[str, str] = {}
    for name in _MODEL_NAMES:
        path = cfg.output_dir / f"model_{name}.pkl"
        save_model(models[name], path)
        model_paths[name] = str(path)
        logger.info("模型保存 %s", path.name)

    write_json(cfg.metrics_path, metrics)
    write_json(cfg.importance_path, importance)
    logger.info("评估指标已写入 metrics.json，特征重要性已写入 feature_importance.json")

    # 输出 user_id / churn_probability / risk_level（最晚快照，LR 决策分数）
    preds = _predict_on_latest_snapshot(models, dataset, cfg)
    preds.to_csv(cfg.predictions_path, index=False, encoding="utf-8-sig")
    logger.info("年度高风险流失用户预测已写入 churn_predictions.csv (%d 人, 其中 high=%d)",
                len(preds), int((preds["risk_level"] == "high").sum()))

    meta = {
        "churn_version": cfg.churn_version,
        "dataset_version": _dataset_version(cfg),
        "task": "churn_prediction",
        "description": "观察窗口内活跃用户 -> 未来30天是否流失（无关键行为且无购买）",
        "churn_definition": (
            "流失：观察窗口 [obs_end-29, obs_end] 内活跃（≥1条行为），"
            "且预测窗口 (obs_end, obs_end+30] 内无关键行为(默认 buy/collect/cart) 且无 paid 订单。"
        ),
        "time_windows": {
            "observation_window": "[obs_end-29, obs_end]（30天，两端含）",
            "prediction_window": "(obs_end, obs_end+30]（30天）",
            "snapshot_range": {
                "start": str(dataset["obs_end"].min()),
                "end": str(dataset["obs_end"].max()),
            },
            "snapshot_step_days": cfg.snapshot_step,
        },
        "leakage_guard": (
            "特征仅使用观察窗口内数据，标签仅使用预测窗口内关键行为与 paid 订单，两窗口不重叠；"
            "train/val/test 按 obs_end 时间先后切分，杜绝未来信息泄漏。"
        ),
        "data_split": {
            "rule": "按 obs_end 时间先后切分，非随机切分",
            "n_snapshots": int(dataset["obs_end"].nunique()),
            "train": {"snapshots": int(train["obs_end"].nunique()), "rows": int(len(train))},
            "val": {"snapshots": int(val["obs_end"].nunique()), "rows": int(len(val))},
            "test": {"snapshots": int(test["obs_end"].nunique()), "rows": int(len(test))},
            "train_ratio": cfg.train_ratio,
            "val_ratio": cfg.val_ratio,
            "test_ratio": cfg.test_ratio,
        },
        "risk_level": {
            "rule": f"churn_probability < {cfg.risk_low_threshold} => low; "
                    f"> {cfg.risk_high_threshold} => high; 其余 => medium",
            "low": int((preds["risk_level"] == "low").sum()),
            "medium": int((preds["risk_level"] == "medium").sum()),
            "high": int((preds["risk_level"] == "high").sum()),
        },
        "models": {
            name: {
                "pipeline": (
                    "StandardScaler -> LogisticRegression(class_weight=balanced)"
                    if "logistic" in name
                    else f"RandomForest(n_estimators={cfg.rf_n_estimators}, class_weight=balanced)"
                ),
                "path": model_paths[name],
            }
            for name in _MODEL_NAMES
        },
        "config": {
            "observation_days": cfg.observation_days,
            "label_days": cfg.label_days,
            "snapshot_step": cfg.snapshot_step,
            "snapshot_ends": list(cfg.snapshot_ends),
            "churn_key_behaviors": list(cfg.churn_key_behaviors),
            "risk_low_threshold": cfg.risk_low_threshold,
            "risk_high_threshold": cfg.risk_high_threshold,
            "random_state": cfg.random_state,
        },
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "dataset": str(dataset_path),
        "metrics": str(cfg.metrics_path),
        "importance": str(cfg.importance_path),
        "predictions": str(cfg.predictions_path),
        "results": list(model_paths.keys()),
    }
    write_json(cfg.meta_path, meta)
    logger.info("流失预测完成 in %ss | 输出: %s", meta["elapsed_seconds"], cfg.output_dir)
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="流失预测: 滚动快照特征+流失标签 -> LR/RF 训练评估 -> data/churn",
    )
    parser.add_argument("--processed-dir", type=str, default=None, help="清洗数据目录（默认 data/processed）")
    parser.add_argument("--interim-dir", type=str, default=None, help="中间产物目录（默认 data/interim）")
    parser.add_argument("--output-dir", type=str, default=None, help="模型输出目录（默认 data/churn）")
    parser.add_argument("--observation-days", type=int, default=None, help="观察窗口天数（默认 30）")
    parser.add_argument("--label-days", type=int, default=None, help="预测窗口天数（默认 30）")
    parser.add_argument("--snapshot-step", type=int, default=None, help="快照步长天数（默认 7）")
    parser.add_argument("--train-ratio", type=float, default=None, help="训练集比例（默认 0.6）")
    parser.add_argument("--val-ratio", type=float, default=None, help="验证集比例（默认 0.2）")
    parser.add_argument("--test-ratio", type=float, default=None, help="测试集比例（默认 0.2）")
    parser.add_argument("--random-state", type=int, default=None, help="随机种子（默认 42）")
    parser.add_argument("--risk-low-threshold", type=float, default=None, help="风险等级 low 阈值（默认 0.3）")
    parser.add_argument("--risk-high-threshold", type=float, default=None, help="风险等级 high 阈值（默认 0.7）")
    parser.add_argument("--rf-n-estimators", type=int, default=None, help="随机森林树数量（默认 200）")
    parser.add_argument("--rf-max-depth", type=int, default=None, help="随机森林最大深度（默认 None）")

    args = parser.parse_args(argv)
    cfg = load_churn_config(
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        output_dir=args.output_dir,
        observation_days=args.observation_days,
        label_days=args.label_days,
        snapshot_step=args.snapshot_step,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        random_state=args.random_state,
        risk_low_threshold=args.risk_low_threshold,
        risk_high_threshold=args.risk_high_threshold,
        rf_n_estimators=args.rf_n_estimators,
        rf_max_depth=args.rf_max_depth,
    )
    run_churn(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())