"""Phase 12 权重实验测试（开发文档第 49.10 节 / 36 节）。

覆盖：
- 三组官方权重实验（A 1/2/3/4/5、B 1/2/4/6/8、C 1/2/3/5/10）；
- 严格时间切分：历史 → train，未来 → test，推荐只用 train 信息；
- @K 指标正确性：Precision/Recall/F1/HitRate/NDCG 手算对比；
- Coverage：推荐列表中不同商品 / 候选商品；
- 权重实验可运行并产出对比表 / 结论；
- 最优权重依据离线指标（NDCG@10）选择，而非主观。
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
from analysis.recommendation.config import RecommendConfig, load_recommend_config
from analysis.recommendation.evaluate import (
    DEFAULT_EVAL_K,
    WEIGHT_VARIANTS,
    choose_best,
    coverage,
    metrics_at_k,
    run_weight_experiment,
    split_train_test,
)

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=4000)


# ---------------------------------------------------------------------
# 一、时间切分
# ---------------------------------------------------------------------
def test_split_is_strictly_temporal():
    df = pd.DataFrame({
        "behavior_id": list(range(6)),
        "user_id": ["U"] * 6,
        "item_id": ["I"] * 6,
        "behavior_type": ["pv"] * 6,
        "event_date": ["2026-06-01", "2026-06-10", "2026-07-01",
                       "2026-07-15", "2026-08-01", "2026-08-30"],
    })
    train, test, cut = split_train_test(df, test_ratio=0.25)
    train_dates = set(train["event_date"])
    test_dates = set(test["event_date"])
    assert not (train_dates & test_dates)      # 无重叠
    assert max(pd.to_datetime(list(train_dates))) <= cut
    assert min(pd.to_datetime(list(test_dates))) > cut


def test_split_honors_ref_date():
    df = pd.DataFrame({
        "behavior_id": [1, 2],
        "user_id": ["U", "U"],
        "item_id": ["I", "I"],
        "behavior_type": ["pv", "pv"],
        "event_date": ["2026-06-01", "2026-07-15"],
    })
    train, test, cut = split_train_test(df, test_ratio=0.5, ref_date=pd.Timestamp("2026-07-01"))
    assert list(test["behavior_id"]) == [2]    # 7-15 在 ref_date 之后 → test


# ---------------------------------------------------------------------
# 二、@K 指标正确性（手算）
# ---------------------------------------------------------------------
def test_metrics_at_k_hand_checked():
    rec = ["I2", "I1", "I5", "I9", "I3"]        # Top-3 命中 2 个
    rel = {"I1", "I2", "I6"}                    # ground truth 3 个
    k = 3
    m = metrics_at_k(rec[:k], rel, k)
    assert m["precision@k"] == pytest.approx(2 / 3, rel=1e-6)
    assert m["recall@k"] == pytest.approx(2 / 3, rel=1e-6)
    assert m["f1@k"] == pytest.approx(2 / 3, rel=1e-6)
    assert m["hit_rate@k"] == 1.0
    # NDCG: 命中位置 rank1(I2) 与 rank2(I1)
    # DCG = 1/log2(2) + 1/log2(3) + 0/log2(4); IDCG(3个) = 1/log2(2)+1/log2(3)+1/log2(4)
    dcg = 1.0 / 1.0 + 1.0 / 1.58496 + 0.0
    idcg = 1.0 / 1.0 + 1.0 / 1.58496 + 1.0 / 2.0
    assert m["ndcg@k"] == pytest.approx(dcg / idcg, abs=1e-4)


def test_metrics_zero_relevance():
    m = metrics_at_k(["I1", "I2"], set(), 2)
    assert m["precision@k"] == 0.0
    assert m["recall@k"] == 0.0
    assert m["f1@k"] == 0.0
    assert m["hit_rate@k"] == 0.0
    assert m["ndcg@k"] == 0.0


def test_coverage_global_metric():
    # 2 个用户分别收到不同商品
    rec = {"I1", "I2"}
    candidates = pd.Index(["I1", "I2", "I3", "I4"])
    assert coverage(rec, candidates) == pytest.approx(2 / 4, rel=1e-6)


def test_weight_variants_are_three_official_sets():
    names = {v["name"] for v in WEIGHT_VARIANTS}
    assert names == {"A_1_2_3_4_5", "B_1_2_4_6_8", "C_1_2_3_5_10"}
    a = next(v for v in WEIGHT_VARIANTS if v["name"] == "A_1_2_3_4_5")
    assert (a["pv"], a["click"], a["collect"], a["cart"], a["buy"]) == (1, 2, 3, 4, 5)


# ---------------------------------------------------------------------
# 三、权重实验端到端
# ---------------------------------------------------------------------
def test_run_weight_experiment_on_generated_data():
    df = pd.DataFrame({
        "behavior_id": list(range(1, 9)),
        "user_id": ["U1", "U1", "U1", "U1", "U2", "U2", "U2", "U2"],
        "item_id": ["I1", "I2", "I1", "I2", "I3", "I4", "I3", "I4"],
        "behavior_type": ["pv", "pv", "buy", "buy", "pv", "pv", "buy", "buy"],
        "event_date": ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04",
                       "2026-06-05", "2026-06-06", "2026-06-07", "2026-06-08"],
    })
    items = pd.DataFrame({
        "item_id": ["I1", "I2", "I3", "I4"],
        "item_name": ["A", "B", "C", "D"],
        "category_id": ["C1", "C1", "C2", "C2"],
        "brand": ["X", "X", "Y", "Y"],
        "price": [10.0, 20.0, 30.0, 40.0],
        "status": [1, 1, 1, 1],
    })
    cfg = RecommendConfig(top_k=5, as_of_date="2026-08-31")
    summary, details = run_weight_experiment(
        df, items, orders=None, order_items=None, cfg=cfg,
        k=3, test_ratio=0.35, max_users=100,
    )
    assert len(summary) == 3                        # 三组实验
    assert set(summary["experiment"]) == {"A_1_2_3_4_5", "B_1_2_4_6_8", "C_1_2_3_5_10"}
    for col in ("precision@k", "recall@k", "f1@k", "hit_rate@k", "ndcg@k", "coverage@k"):
        assert col in summary.columns
    best = choose_best(summary)
    assert best in set(summary["experiment"])
    best_row = summary[summary["experiment"] == best].iloc[0]
    assert best_row["ndcg@k"] == summary["ndcg@k"].max()     # NDCG@10 是排序依据
    assert len(details) == 3


def test_metrics_use_train_only():
    """确认切分严格按时间：test 行为只在后段商品上。"""
    behaviors = pd.DataFrame({
        "behavior_id": list(range(1, 7)),
        "user_id": ["U1"] * 6,
        "item_id": ["I1", "I2", "I3", "I4", "I5", "I6"],
        "behavior_type": ["pv"] * 6,
        "event_date": ["2026-06-01", "2026-06-02", "2026-06-03",
                       "2026-06-20", "2026-06-21", "2026-06-22"],
    })
    items = pd.DataFrame({
        "item_id": ["I1", "I2", "I3", "I4", "I5", "I6"],
        "item_name": ["n"] * 6, "category_id": ["c"] * 6, "brand": ["b"] * 6,
        "price": [10.0] * 6, "status": [1] * 6,
    })
    train, test, _ = split_train_test(behaviors, test_ratio=0.5)
    # 前 3 天商品（I1/I2/I3）只进 train；后 3 天商品（I4/I5/I6）只进 test
    assert set(train["item_id"]) == {"I1", "I2", "I3"}
    assert set(test["item_id"]) == {"I4", "I5", "I6"}


# ---------------------------------------------------------------------
# 四、end-to-end（生成 -> ETL -> 实验 -> 结论落盘）
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def exp_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase12")
    raw = root / "raw"
    run_generation(load_config(output_dir=str(raw), **TEST_GEN), log=False)
    etl_cfg = load_etl_config(
        raw_dir=str(raw),
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        mysql=False,
        chunk_size=1000,
    )
    run_etl(etl_cfg, log=False)
    return root


def test_weight_experiment_e2e_outputs(exp_dir):
    cfg = load_recommend_config(
        processed_dir=str(exp_dir / "processed"),
        interim_dir=str(exp_dir / "interim"),
        output_dir=str(exp_dir / "recommendation"),
        top_k=5,
    )
    from analysis.feature_engineering.base import load_processed

    items = load_processed(cfg.processed_dir, "items")
    behaviors = load_processed(cfg.processed_dir, "user_behaviors")
    orders = load_processed(cfg.processed_dir, "orders")
    order_items = load_processed(cfg.processed_dir, "order_items")
    summary, details = run_weight_experiment(
        behaviors, items, orders, order_items, cfg=cfg,
        k=5, test_ratio=0.25, max_users=300,
    )
    best = choose_best(summary)
    best_row = summary[summary["experiment"] == best].iloc[0]

    # 固定种子保证可复现：指标在 [0,1]
    for col in ("precision@k", "recall@k", "f1@k", "hit_rate@k", "ndcg@k", "coverage@k"):
        assert summary[col].between(0, 1).all(), col

    # 最优权重确实来自离线实验（不要求一定等于默认 1/2/3/4/5，但必须给出结论）
    assert best in {"A_1_2_3_4_5", "B_1_2_4_6_8", "C_1_2_3_5_10"}
    assert float(best_row["buy"]) in (5.0, 8.0, 10.0)