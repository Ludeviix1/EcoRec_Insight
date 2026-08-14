"""Phase 13 Content-Based 推荐测试（开发文档第 49.11 节 / 35.4 节）。

覆盖：
- 内容特征：category / brand / price_range / item tags 构造商品向量；
- 相似度：同分类/同品牌商品余弦相似度更高；
- 推荐流程：用户历史种子 → 内容相似 → 分数累加 → 过滤 → Top-K；
- 过滤：已购买 / 已下架 / 不存在 / 重复；
- 冷启动：新商品（无行为也可被内容召回）；新用户回退全局热门；
- 统一接口：recommend(user_id, top_k) 返回 item_id/score/reason；
- end-to-end：生成 -> ETL -> Content 构建 -> 模型/推荐/元数据落盘。
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
from analysis.recommendation.content import ContentRecommender, build_content_matrix
from analysis.recommendation.run import build_content

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


def _items() -> pd.DataFrame:
    return pd.DataFrame({
        "item_id": ["I1", "I2", "I3", "I4", "I5", "I6"],
        "item_name": ["华为 手机 500", "华为 平板 600", "小米 手机 700",
                      "小米 耳机 800", "苏泊尔 锅 900", "下架品 未知 000"],
        "category_id": ["C01", "C01", "C02", "C02", "C03", "C99"],
        "brand": ["华为", "华为", "小米", "小米", "苏泊尔", "其它"],
        "price": [3999.0, 2999.0, 1999.0, 999.0, 199.0, 50.0],
        "stock": [100.0, 100.0, 100.0, 100.0, 100.0, 50.0],
        "status": [1, 1, 1, 1, 1, 0],       # I6 下架
        "created_at": ["2026-01-01"] * 6,
    })


def _behaviors() -> pd.DataFrame:
    rows = [
        # U1 浏览/购买过手机类（I1、I3）
        {"behavior_id": "B1", "user_id": "U1", "item_id": "I1", "behavior_type": "buy",
         "event_time": "2026-08-30 10:00:00", "event_date": "2026-08-30",
         "event_hour": 10, "device_type": "pc", "channel": "organic"},
        {"behavior_id": "B2", "user_id": "U1", "item_id": "I3", "behavior_type": "pv",
         "event_time": "2026-08-29 10:00:00", "event_date": "2026-08-29",
         "event_hour": 10, "device_type": "pc", "channel": "organic"},
        # U2 只浏览过小米（I3、I4）
        {"behavior_id": "B3", "user_id": "U2", "item_id": "I3", "behavior_type": "pv",
         "event_time": "2026-08-28 10:00:00", "event_date": "2026-08-28",
         "event_hour": 10, "device_type": "pc", "channel": "organic"},
        {"behavior_id": "B4", "user_id": "U2", "item_id": "I4", "behavior_type": "pv",
         "event_time": "2026-08-28 10:00:00", "event_date": "2026-08-28",
         "event_hour": 10, "device_type": "pc", "channel": "organic"},
    ]
    return pd.DataFrame(rows)


def _orders() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1"],
        "user_id": ["U1"],
        "order_time": ["2026-08-30 11:00:00"],
        "total_amount": [3999.0],
        "status": ["paid"],
        "payment_method": ["balance"],
    })


def _order_items() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1"],
        "item_id": ["I1"],
        "quantity": [1],
        "unit_price": [3999.0],
        "amount": [3999.0],
    })


def _model():
    cfg = RecommendConfig()
    return ContentRecommender(cfg).fit(_behaviors(), _items(), _orders(), _order_items())


# ---------------------------------------------------------------------
# 一、内容特征与向量
# ---------------------------------------------------------------------
def test_build_content_matrix_has_category_brand_price_tag():
    X, index, info = build_content_matrix(_items(), n_price_bins=3)
    assert X.shape[0] == len(index) == 6
    assert X.shape[1] >= 6            # 分类+品牌+价格档+标签 至少 6 维
    assert info["n_price_bins"] >= 1
    assert "华为 手机" in " ".join(info["tag_example"]) or "手机" in " ".join(info["tag_example"])


def test_same_category_items_are_most_similar():
    X, index, _ = build_content_matrix(_items(), n_price_bins=3)
    # I1(华为手机) 与 I2(华为平板) 同分类 C01 → 相似度应高于 I1 vs I5(苏泊尔锅)
    import numpy as np
    i1, i2, i5 = index.get_loc("I1"), index.get_loc("I2"), index.get_loc("I5")
    m = (X @ X.T).toarray()
    assert m[i1, i2] > m[i1, i5]


# ---------------------------------------------------------------------
# 二、推荐行为
# ---------------------------------------------------------------------
def test_recommend_prefers_same_category_filled_from_seed():
    model = _model()
    recs = model.recommend("U1", top_k=5)
    ids = [r["item_id"] for r in recs]
    assert "I1" not in ids                # 已购买
    assert "I6" not in ids                # 下架
    assert len(recs) <= 5
    assert all(r["reason"] for r in recs)
    # U1 种子是 I1(华为/C01) 与 I3(小米/C02)；I2 与 I1 完全同分类+同品牌 → 应排第一
    assert recs[0]["item_id"] == "I2"


def test_recommend_continuous_interface():
    recs = _model().recommend("U1", top_k=3)
    assert set(recs[0].keys()) >= {"item_id", "item_name", "category_id", "brand", "price", "score", "reason"}


def test_new_user_cold_start_returns_global_fallback():
    model = _model()
    recs = model.recommend("NEVER_SEEN", top_k=5)
    assert isinstance(recs, list)
    # 新用户无种子 → 全局热门兜底（至少非空）
    assert len(recs) >= 1


def test_new_item_is_recallable_without_behavior():
    """冷启动商品：从未被用户交互，但内容特征（与种子同分类/品牌）能召回它。"""
    items = _items().copy()
    # 追加一个全新商品同分类 C01、同品牌 华为（无任何行为）
    items = pd.concat([
        items,
        pd.DataFrame([{
            "item_id": "I7", "item_name": "华为 手表 321", "category_id": "C01", "brand": "华为",
            "price": 1499.0, "stock": 50.0, "status": 1, "created_at": "2026-08-01",
        }]),
    ], ignore_index=True)
    model = ContentRecommender(RecommendConfig()).fit(_behaviors(), items, _orders(), _order_items())
    recs = model.recommend("U1", top_k=10)
    ids = [r["item_id"] for r in recs]
    assert "I7" in ids      # 无行为新商品也被内容相似召回


# ---------------------------------------------------------------------
# 三、end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def content_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase13")
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
    build_content(rcfg, log=False)
    return root / "recommendation"


def test_build_content_outputs(content_dir):
    assert (content_dir / "content_model.joblib").exists()
    assert (content_dir / "content_recommendations.csv").exists()
    assert (content_dir / "content_meta.json").exists()

    meta = json.loads((content_dir / "content_meta.json").read_text(encoding="utf-8"))
    assert meta["algorithm"] == "content"
    assert meta["task"] == "content_based"
    assert "category(one-hot)" in meta["features"]
    assert meta["similarity"] == "cosine similarity"
    assert meta["stats"]["n_items_embedded"] >= 1
    assert meta["stats"]["n_recommendations"] >= 1
    assert meta["filtering"]["off_shelf"] is True

    model = joblib.load(content_dir / "content_model.joblib")
    assert model._item_index is not None
    assert model._X is not None

    rec = pd.read_csv(content_dir / "content_recommendations.csv", encoding="utf-8-sig")
    assert set(rec.columns) >= {"user_id", "item_id", "score", "reason"}
    assert len(rec) == rec["user_id"].nunique() * 5        # top_k=5