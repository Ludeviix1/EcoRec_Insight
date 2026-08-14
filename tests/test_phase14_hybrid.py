"""Phase 14 Hybrid 推荐测试（开发文档第 49.12 节 / 35.2 / 35.3 / 35.5 节）。

覆盖：
- ItemCF：user-item 矩阵行为加权（pv=1..buy=5）、item-item 余弦、按种子累加；
- UserCF：user-user 余弦、相似用户喜欢的商品加权；
- Content 分量在 Hybrid 中复用 `score_candidates`；
- Hybrid：四路分数归一化到 [0,1] 后加权融合（权重可配置）；
- 过滤：已购买 / 已下架被剔除；
- 冷启动：各分量为新用户回退；
- 统一接口 recommend(user_id, top_k)；
- baseline vs hybrid 离线对比可运行并依据评估指标给出结论。
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl
from analysis.recommendation.config import RecommendConfig, load_recommend_config
from analysis.recommendation.evaluate import compare_algorithms
from analysis.recommendation.hybrid import DEFAULT_HYBRID_WEIGHTS, HybridRecommender
from analysis.recommendation.itemcf import ItemCFRecommender
from analysis.recommendation.run import build_hybrid
from analysis.recommendation.usercf import UserCFRecommender

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=4000)


def _items() -> pd.DataFrame:
    return pd.DataFrame({
        "item_id": ["I1", "I2", "I3", "I4", "I5"],
        "item_name": ["手机A", "手机B", "平板A", "耳机A", "锅A"],
        "category_id": ["C01", "C01", "C02", "C02", "C03"],
        "brand": ["华为", "华为", "小米", "小米", "苏泊尔"],
        "price": [3999.0, 2999.0, 1999.0, 999.0, 199.0],
        "stock": [100.0] * 5,
        "status": [1, 1, 1, 1, 0],          # I5 下架
        "created_at": ["2026-01-01"] * 5,
    })


def _behaviors() -> pd.DataFrame:
    rows = []
    # U1 买过 I1、I2；U2 买过 I1、I3（与 U1 相似）；U3 买过 I4、I2
    specs = [
        ("U1", "I1", "buy"), ("U1", "I2", "buy"),
        ("U2", "I1", "buy"), ("U2", "I3", "buy"),
        ("U3", "I4", "buy"), ("U3", "I2", "buy"),
        ("U4", "I4", "pv"),  ("U4", "I1", "pv"),
    ]
    for i, (uid, item, bt) in enumerate(specs):
        rows.append({
            "behavior_id": f"B{i}", "user_id": uid, "item_id": item, "behavior_type": bt,
            "event_time": "2026-08-30 10:00:00", "event_date": "2026-08-30",
            "event_hour": 10, "device_type": "pc", "channel": "organic",
        })
    return pd.DataFrame(rows)


def _orders() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1"],
        "user_id": ["U3"],
        "order_time": ["2026-08-30 11:00:00"],
        "total_amount": [999.0],
        "status": ["paid"],
        "payment_method": ["balance"],
    })


def _order_items() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1"], "item_id": ["I4"],
        "quantity": [1], "unit_price": [999.0], "amount": [999.0],
    })


def _cfg() -> RecommendConfig:
    return RecommendConfig()


# ---------------------------------------------------------------------
# 一、ItemCF
# ---------------------------------------------------------------------
def test_itemcf_matrix_weights_and_neighbors():
    model = ItemCFRecommender(_cfg()).fit(_behaviors(), _items(), _orders(), _order_items())
    assert model._U is not None
    assert model._item_index is not None
    # U4 只 pv/click I1、I4，但 U1 买过 I2 → ItemCF 应推荐 I2
    recs = model.recommend("U4", top_k=10)
    ids = [r["item_id"] for r in recs]
    assert "I2" in ids
    assert "I5" not in ids      # 下架
    assert all(r["reason"] for r in recs)


def test_itemcf_cold_start_fallback():
    model = ItemCFRecommender(_cfg()).fit(_behaviors(), _items(), _orders(), _order_items())
    recs = model.recommend("NEVER_SEEN", top_k=5)
    assert len(recs) >= 1


# ---------------------------------------------------------------------
# 二、UserCF
# ---------------------------------------------------------------------
def test_usercf_recommends_similar_users_items():
    model = UserCFRecommender(_cfg(), n_neighbors=10).fit(_behaviors(), _items(), _orders(), _order_items())
    # U1 与 U2/I3 共享 I1 行为 → U1 应被推荐 U2 喜欢的 I3
    recs = model.recommend("U1", top_k=10)
    ids = [r["item_id"] for r in recs]
    assert "I3" in ids or "I4" in ids      # 相似用户（U2/U3）喜欢的商品
    assert "I5" not in ids


def test_usercf_unknown_user_fallback():
    model = UserCFRecommender(_cfg(), n_neighbors=10).fit(_behaviors(), _items(), _orders(), _order_items())
    recs = model.recommend("GHOST", top_k=5)
    assert len(recs) >= 1


# ---------------------------------------------------------------------
# 三、Hybrid
# ---------------------------------------------------------------------
def test_hybrid_includes_all_components_scores():
    model = HybridRecommender(_cfg()).fit(_behaviors(), _items(), _orders(), _order_items())
    comps = model.score_candidates("U1", pd.Index(["I1", "I2", "I3", "I4"]))
    assert set(comps.columns) == {"itemcf", "usercf", "popular", "content"}
    # 每列是 minmax 后的分量（权重 0 时恒 0；这里默认权重非 0）
    assert (comps >= 0).all().all() and (comps <= 1).all().all()


def test_hybrid_weights_are_configurable():
    w = {"itemcf": 0.0, "usercf": 0.0, "popular": 0.0, "content": 1.0}
    model = HybridRecommender(_cfg(), hybrid_weights=w).fit(_behaviors(), _items(), _orders(), _order_items())
    # content 权重为 1、其余为 0 → 结果等效 Content
    rank_h = [r["item_id"] for r in model.recommend("U1", top_k=5)]
    from analysis.recommendation.content import ContentRecommender
    model_c = ContentRecommender(_cfg()).fit(_behaviors(), _items(), _orders(), _order_items())
    rank_c = [r["item_id"] for r in model_c.recommend("U1", top_k=5)]
    assert rank_h == rank_c


def test_hybrid_filters_purchased_and_off_shelf():
    model = HybridRecommender(_cfg()).fit(_behaviors(), _items(), _orders(), _order_items())
    recs = model.recommend("U3", top_k=10)      # U3 已购买 I4（paid 订单）
    ids = [r["item_id"] for r in recs]
    assert "I4" not in ids      # 已购买
    assert "I5" not in ids      # 下架


def test_hybrid_interface_contract():
    model = HybridRecommender(_cfg()).fit(_behaviors(), _items(), _orders(), _order_items())
    recs = model.recommend("U1", top_k=3)
    assert isinstance(recs, list) and len(recs) <= 3
    assert set(recs[0].keys()) >= {"item_id", "item_name", "category_id", "brand", "price", "score", "reason"}
    assert "混合召回" in recs[0]["reason"]


def test_default_hybrid_weights():
    assert set(DEFAULT_HYBRID_WEIGHTS.keys()) == {"itemcf", "usercf", "popular", "content"}
    assert abs(sum(DEFAULT_HYBRID_WEIGHTS.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------
# 四、baseline vs hybrid 对比 + end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def hybrid_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase14")
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
    rcfg = load_recommend_config(
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        output_dir=str(root / "recommendation"),
        top_k=5,
    )
    build_hybrid(rcfg, log=False)
    return root / "recommendation"


def test_build_hybrid_outputs(hybrid_dir):
    assert (hybrid_dir / "hybrid_model.joblib").exists()
    assert (hybrid_dir / "hybrid_recommendations.csv").exists()
    assert (hybrid_dir / "hybrid_meta.json").exists()

    meta = json.loads((hybrid_dir / "hybrid_meta.json").read_text(encoding="utf-8"))
    assert meta["algorithm"] == "hybrid"
    assert set(meta["hybrid_weights"].keys()) == {"itemcf", "usercf", "popular", "content"}
    assert "HybridScore" in meta["formula"]
    assert meta["stats"]["n_recommendations"] >= 1

    model = joblib.load(hybrid_dir / "hybrid_model.joblib")
    recs = model.recommend("U000001", top_k=5)
    assert len(recs) <= 5
    if recs:
        assert set(recs[0].keys()) >= {"item_id", "score", "reason"}


def test_compare_algorithms_readable_and_baseline_compared():
    """baseline vs hybrid 对比必须可运行，且结论依据评估指标。"""
    # 用小数据集跑 compare_algorithms → 至少能产出 popular 与 hybrid 两行指标
    summary, details = compare_algorithms(
        _behaviors(), _items(), _orders(), _order_items(), cfg=_cfg(),
        algorithms=["popular", "itemcf", "usercf", "content", "hybrid"],
        k=5, test_ratio=0.4, max_users=50,
    )
    assert set(summary["algorithm"]) == {"popular", "itemcf", "usercf", "content", "hybrid"}
    for col in ("precision@k", "recall@k", "f1@k", "hit_rate@k", "ndcg@k", "coverage@k"):
        assert summary[col].between(0, 1).all(), col
    # Hybrid 结论基于 NDCG 排序：rank=1 是 ndcg@k 最大者
    assert summary.loc[summary["rank"] == 1, "ndcg@k"].iloc[0] == summary["ndcg@k"].max()
    assert len(details) == 5