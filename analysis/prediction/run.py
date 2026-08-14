"""购买预测全量入口（Phase 9，开发文档第 49.7 节）。

流程：
    data/processed 六张清洗 CSV
        ↓ 滚动快照构建样本集（观察窗口特征 + 未来 7 天购买标签）
    time split -> LR / RF 训练与评估
        ↓
    data/prediction/ 模型 .pkl + metrics.json + feature_importance.json + prediction_meta.json
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from analysis.etl.pipeline import run_etl  # noqa: F401  # 保持与其它 Phase 一致的导入面

from .config import PREDICTION_FEATURE_COLS, PredictionConfig, load_prediction_config
from .data import build_snapshot_dataset, resolve_dataset_range
from .model import save_model, time_split, train_and_evaluate, write_json

logger = logging.getLogger("analysis.prediction")

_MODEL_NAMES = ("logistic_regression", "random_forest")


def _dataset_version(cfg: PredictionConfig) -> str:
    p = cfg.interim_dir / "etl_meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("dataset_version", "unknown")
        except Exception:
            return "unknown"
    return "unknown"


def run_prediction(cfg: PredictionConfig | None = None, *, log: bool = True) -> dict:
    """执行购买预测，返回运行记录 dict（已落盘 data/prediction/prediction_meta.json）。"""
    cfg = cfg or load_prediction_config()
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

    dataset = build_snapshot_dataset(users, behaviors, orders, order_items, items, cfg)
    dataset_path = cfg.output_dir / "snapshot_dataset.csv"
    dataset.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    logger.info("样本集写入 %s (%d 行)", dataset_path.name, len(dataset))

    earliest, latest = resolve_dataset_range(cfg, behaviors)
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

    meta = {
        "prediction_version": cfg.prediction_version,
        "dataset_version": _dataset_version(cfg),
        "task": "purchase_prediction",
        "description": "过去30天行为特征 -> 未来7天是否购买（二分类）",
        "time_windows": {
            "observation_days": cfg.observation_days,
            "label_days": cfg.label_days,
            "snapshot_range": {"start": str(earliest.date()), "end": str(latest.date())},
            "snapshot_step_days": cfg.snapshot_step,
        },
        "leakage_guard": (
            "特征仅使用观察窗口 [obs_end-29, obs_end] 内数据，标签仅使用预测窗口 "
            "(obs_end, obs_end+7] 内 paid 订单，两窗口不重叠；"
            "train/val/test 按 obs_end 时间先后切分，杜绝未来信息泄漏。"
        ),
        "class_imbalance": "类别不平衡时不以 Accuracy 为准，采用 Precision/Recall/F1/ROC-AUC/PR-AUC/混淆矩阵，并报告 positive_rate。",
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
        "features": {
            "n_features": len(PREDICTION_FEATURE_COLS),
            "columns": list(PREDICTION_FEATURE_COLS),
        },
        "models": {
            "logistic_regression": {
                "pipeline": "StandardScaler -> LogisticRegression(class_weight=balanced)",
                "max_iter": cfg.lr_max_iter,
                "path": model_paths["logistic_regression"],
            },
            "random_forest": {
                "n_estimators": cfg.rf_n_estimators,
                "max_depth": cfg.rf_max_depth,
                "class_weight": "balanced",
                "path": model_paths["random_forest"],
            },
        },
        "config": {
            "observation_days": cfg.observation_days,
            "label_days": cfg.label_days,
            "snapshot_step": cfg.snapshot_step,
            "snapshot_ends": list(cfg.snapshot_ends),
            "random_state": cfg.random_state,
        },
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "dataset": str(dataset_path),
        "metrics": str(cfg.metrics_path),
        "importance": str(cfg.importance_path),
        "results": list(model_paths.keys()),
    }
    write_json(cfg.meta_path, meta)
    logger.info("购买预测完成 in %ss | 输出: %s", meta["elapsed_seconds"], cfg.output_dir)
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="购买预测: 滚动快照特征+标签 -> LR/RF 训练评估 -> data/prediction",
    )
    parser.add_argument("--processed-dir", type=str, default=None, help="清洗数据目录（默认 data/processed）")
    parser.add_argument("--interim-dir", type=str, default=None, help="中间产物目录（默认 data/interim）")
    parser.add_argument("--output-dir", type=str, default=None, help="模型输出目录（默认 data/prediction）")
    parser.add_argument("--observation-days", type=int, default=None, help="观察窗口天数（默认 30）")
    parser.add_argument("--label-days", type=int, default=None, help="预测窗口天数（默认 7）")
    parser.add_argument("--snapshot-step", type=int, default=None, help="快照步长天数（默认 7）")
    parser.add_argument("--train-ratio", type=float, default=None, help="训练集比例（默认 0.6）")
    parser.add_argument("--val-ratio", type=float, default=None, help="验证集比例（默认 0.2）")
    parser.add_argument("--test-ratio", type=float, default=None, help="测试集比例（默认 0.2）")
    parser.add_argument("--random-state", type=int, default=None, help="随机种子（默认 42）")
    parser.add_argument("--rf-n-estimators", type=int, default=None, help="随机森林树数量（默认 200）")
    parser.add_argument("--rf-max-depth", type=int, default=None, help="随机森林最大深度（默认 None）")

    args = parser.parse_args(argv)
    cfg = load_prediction_config(
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
        rf_n_estimators=args.rf_n_estimators,
        rf_max_depth=args.rf_max_depth,
    )
    run_prediction(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())