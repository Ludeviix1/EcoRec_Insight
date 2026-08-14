"""Phase 18 核心链路回归测试（开发文档第 49.16 节）。

不重复各阶段深测，而是用统一契约跨 5 个算法（Popular / ItemCF / UserCF / Content / Hybrid）
验证"核心链路不被修改破坏"：
- Top-K 契约：len<=top_k、item_id 无重复、score 非增、reason 非空、均为在架且存在商品；
- 推荐过滤：已购买（paid 订单）剔除、已下架剔除；
- 冷启动：全新用户（无行为）所有算法不崩溃且返回有效结果；新商品可被 Content 内容召回；
- 数据质量不变量：行为/订单明细引用的商品必须存在于商品维度。

运行：python -m pytest tests/test_phase18_core.py -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from analysis.recommendation.config import RecommendConfig
from analysis.recommendation.content import ContentRecommender
from analysis.recommendation.hybrid import HybridRecommender
from analysis.recommendation.itemcf import ItemCFRecommender
from analysis.recommendation.popular import PopularRecommender
from analysis.recommendation.usercf import UserCFRecommender


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


RECOMMENDERS: list[tuple[str, type]] = [
    ("popular", PopularRecommender),
    ("itemcf", ItemCFRecommender),
    ("usercf", UserCFRecommender),
    ("content", ContentRecommender),
    ("hybrid", HybridRecommender),
]

_ON_SHELF = {"I1", "I2", "I3", "I4"}   # I5 下架


@pytest.fixture(params=RECOMMENDERS, ids=[n for n, _ in RECOMMENDERS])
def model(request) -> tuple[str, object]:
    name, cls = request.param
    cfg = RecommendConfig()
    m = cls(cfg).fit(_behaviors(), _items(), _orders(), _order_items())
    return name, m


# ---------------------------------------------------------------------
# 一、数据质量不变量（推荐输入必须满足，否则核心链路断裂）
# ---------------------------------------------------------------------
def test_data_quality_invariants():
    items = _items()
    item_ids = set(items["item_id"])
    assert _behaviors()["item_id"].isin(item_ids).all(), "行为引用了不存在的商品"
    assert _order_items()["item_id"].isin(item_ids).all(), "订单明细引用了不存在的商品"
    paid = _orders().loc[_orders()["status"] == "paid", "order_id"]
    assert set(paid).issubset(set(_order_items()["order_id"])), "paid 订单缺少订单明细"


# ---------------------------------------------------------------------
# 二、Top-K 契约（所有算法统一）
# ---------------------------------------------------------------------
def test_top_k_contract(model):
    name, m = model
    recs = m.recommend("U2", top_k=3)
    assert isinstance(recs, list)
    assert len(recs) <= 3, f"{name}: len(recs)={len(recs)} > top_k"
    ids = [r["item_id"] for r in recs]
    assert len(ids) == len(set(ids)), f"{name}: 推荐出现重复商品"
    scores = [r["score"] for r in recs]
    assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)), f"{name}: score 未按降序"
    for r in recs:
        assert r["reason"], f"{name}: reason 为空"
        assert r["item_id"] in _ON_SHELF, f"{name}: 推荐了不存在的/下架商品 {r['item_id']}"


def test_top_k_less_than_candidates_when_small(model):
    name, m = model
    # top_k 大于候选数时不应报错，且不超候选数
    recs = m.recommend("U2", top_k=100)
    assert len(recs) <= len(_ON_SHELF)


# ---------------------------------------------------------------------
# 三、推荐过滤
# ---------------------------------------------------------------------
def test_filter_purchased(model):
    name, m = model
    # U3 已购买 I4（O1 paid），各算法必须剔除
    recs = m.recommend("U3", top_k=10)
    ids = [r["item_id"] for r in recs]
    assert "I4" not in ids, f"{name}: 未过滤已购买商品 I4"


def test_filter_off_shelf(model):
    name, m = model
    for uid in ("U1", "U2", "U3", "U4"):
        recs = m.recommend(uid, top_k=10)
        ids = [r["item_id"] for r in recs]
        assert "I5" not in ids, f"{name}: 未过滤下架商品 I5（用户 {uid}）"


# ---------------------------------------------------------------------
# 四、冷启动
# ---------------------------------------------------------------------
def test_cold_start_new_user(model):
    name, m = model
    recs = m.recommend("NEVER_SEEN", top_k=5)
    assert isinstance(recs, list)
    for r in recs:
        assert r["item_id"] in _ON_SHELF, f"{name}: 冷启动推荐了无效商品"
        assert r["score"] >= 0.0 and r["reason"]


def test_cold_start_new_item_recallable_by_content():
    """冷启动商品：从未被用户交互，但内容特征（与种子同分类/品牌）能召回它。"""
    items = pd.concat([
        _items(),
        pd.DataFrame([{
            "item_id": "I6", "item_name": "手机C", "category_id": "C01",
            "brand": "华为", "price": 4999.0, "stock": 50.0, "status": 1,
            "created_at": "2026-01-01",
        }]),
    ], ignore_index=True)
    m = ContentRecommender(RecommendConfig()).fit(_behaviors(), items, _orders(), _order_items())
    recs = m.recommend("U1", top_k=10)
    assert "I6" in [r["item_id"] for r in recs]


# ---------------------------------------------------------------------
# 五、接口稳定性：所有算法返回相同字段集合
# ---------------------------------------------------------------------
def test_recommend_row_schema_consistent(model):
    name, m = model
    recs = m.recommend("U2", top_k=3)
    if not recs:
        pytest.skip(f"{name}: 无候选")
    keys = set(recs[0].keys())
    assert {"item_id", "item_name", "category_id", "brand", "price", "score", "reason"} <= keys
    for r in recs:
        assert set(r.keys()) == keys, f"{name}: 行字段不一致"
