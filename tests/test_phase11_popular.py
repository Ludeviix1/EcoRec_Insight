"""Phase 11 Popular Baseline 测试（开发文档第 49.9 节 / 35 节）。

覆盖：
- 热度分公式：行为加权（默认 pv/click/collect/cart/buy = 1/2/3/4/5）；
- 时间衰减：越近的行为权重越高，half_life 可配置，half_life<=0 时不做衰减；
- 标准化：各行为分量与最终热度分落在 [0,1]；
- 过滤：已购买 / 已下架 / 不存在 / 重复商品被剔除；
- 冷启动：新用户（无行为记录）仍能得到全局热门 Top-K；
- 统一接口：recommend(user_id, top_k) 返回 item_id/score/reason；
- end-to-end：生成 -> ETL -> Popular 构建 -> 模型/推荐/元数据落盘。
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
from analysis.recommendation.base import minmax_01, time_decay_weight
from analysis.recommendation.config import RecommendConfig, load_recommend_config
from analysis.recommendation.popular import PopularRecommender
from analysis.recommendation.run import build_popular

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)

OBS_HALF_LIFE = 7.0


def _items() -> pd.DataFrame:
    return pd.DataFrame({
        "item_id": ["I1", "I2", "I3"],
        "item_name": ["手机A", "手机B", "下架品"],
        "category_id": ["C01", "C02", "C03"],
        "brand": ["华为", "小米", "其它"],
        "price": [3999.0, 2999.0, 199.0],
        "stock": [100.0, 200.0, 50.0],
        "status": [1, 1, 0],            # I3 下架
        "created_at": ["2026-01-01", "2026-01-01", "2026-01-01"],
    })


def _behaviors() -> pd.DataFrame:
    today = pd.Timestamp("2026-08-31")
    def ts(days_ago, h=10):
        d = today - pd.Timedelta(days=days_ago)
        return str(d.replace(hour=h))
    rows = []
    for i, offset in enumerate(range(14)):  # I1: 14 条 pv，都为最近
        rows.append({
            "behavior_id": f"B1-{i}", "user_id": "U1", "item_id": "I1", "behavior_type": "pv",
            "event_time": ts(offset), "event_date": str((today - pd.Timedelta(days=offset)).date()),
            "event_hour": 10, "device_type": "pc", "channel": "organic",
        })
    return pd.DataFrame(rows)


def _orders() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1"],
        "user_id": ["U2"],
        "order_time": ["2026-08-20 10:00:00"],
        "total_amount": [100.0],
        "status": ["paid"],
        "payment_method": ["balance"],
    })


def _order_items() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1"],
        "item_id": ["I2"],
        "quantity": [1],
        "unit_price": [100.0],
        "amount": [100.0],
    })


# ---------------------------------------------------------------------
# 一、时间衰减与标准化
# ---------------------------------------------------------------------
def test_time_decay_older_events_weight_less():
    ref = pd.Timestamp("2026-08-31")
    dates = pd.Series(["2026-08-24", "2026-08-31"], dtype=str)   # 7 天前 vs 当天
    w = time_decay_weight(dates, ref, half_life=7.0)
    assert w.iloc[0] < w.iloc[1]
    assert abs(w.iloc[0] - 0.5) < 1e-6      # 正好一个半衰期 => 0.5
    assert abs(w.iloc[1] - 1.0) < 1e-6


def test_time_decay_no_decay_when_half_life_zero():
    ref = pd.Timestamp("2026-08-31")
    dates = pd.Series(["2026-06-01", "2026-08-31"])
    w = time_decay_weight(dates, ref, half_life=0.0)
    assert (w == 1.0).all()


def test_minmax_standardizes_to_unit_interval():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    out = minmax_01(s)
    assert out.min() == 0.0 and out.max() == 1.0
    assert ((out >= 0) & (out <= 1)).all()


def test_score_in_unit_interval():
    cfg = RecommendConfig()
    model = PopularRecommender(cfg).fit(_behaviors(), _items(), _orders(), _order_items())
    assert ((model.score_table["score"] >= 0) & (model.score_table["score"] <= 1)).all()


# ---------------------------------------------------------------------
# 二、热门排序与权重
# ---------------------------------------------------------------------
def test_popular_ranks_by_weighted_behaviors():
    cfg = RecommendConfig()
    # I1 大量 pv；新增 I2 少量 buy（buy 权重 5 更高）
    behaviors = pd.concat([
        _behaviors(),
        pd.DataFrame([{
            "behavior_id": "B2-0", "user_id": "U3", "item_id": "I2", "behavior_type": "buy",
            "event_time": "2026-08-31 10:00:00", "event_date": "2026-08-31",
            "event_hour": 10, "device_type": "pc", "channel": "organic",
        }]),
    ], ignore_index=True)
    model = PopularRecommender(cfg).fit(behaviors, _items(), _orders(), _order_items())
    order = list(model.score_table.index)
    assert order[0] == "I2"      # buy(权重5) 的单条行为热度高于 14 条 pv(权重1)


def test_popular_cold_start_user_gets_global_top_k():
    cfg = RecommendConfig()
    model = PopularRecommender(cfg).fit(_behaviors(), _items(), _orders(), _order_items())
    recs = model.recommend("NEVER_SEEN_USER", top_k=10)      # 无任何行为的新用户
    assert len(recs) >= 1
    assert recs[0]["item_id"] == "I1"                        # 全局最热商品
    assert recs[0]["reason"]


# ---------------------------------------------------------------------
# 三、过滤
# ---------------------------------------------------------------------
def test_filter_purchased_and_off_shelf():
    cfg = RecommendConfig()
    behaviors = pd.concat([
        _behaviors(),
        pd.DataFrame([
            {"behavior_id": "B2", "user_id": "U2", "item_id": "I2", "behavior_type": "buy",
             "event_time": "2026-08-31 10:00:00", "event_date": "2026-08-31",
             "event_hour": 10, "device_type": "pc", "channel": "organic"},
            {"behavior_id": "B3", "user_id": "U3", "item_id": "I3", "behavior_type": "pv",
             "event_time": "2026-08-31 10:00:00", "event_date": "2026-08-31",
             "event_hour": 10, "device_type": "pc", "channel": "organic"},
        ]),
    ], ignore_index=True)
    model = PopularRecommender(cfg).fit(behaviors, _items(), _orders(), _order_items())
    recs = model.recommend("U2", top_k=10)
    ids = [r["item_id"] for r in recs]
    assert "I2" not in ids        # U2 已购买 I2（O1）
    assert "I3" not in ids        # I3 下架


def test_recommend_interface_contract():
    cfg = RecommendConfig()
    model = PopularRecommender(cfg).fit(_behaviors(), _items(), _orders(), _order_items())
    recs = model.recommend("U1", top_k=3)
    assert isinstance(recs, list) and len(recs) <= 3
    assert set(recs[0].keys()) >= {"item_id", "item_name", "category_id", "brand", "price", "score", "reason"}


# ---------------------------------------------------------------------
# 四、end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def rec_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase11")
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
    build_popular(rcfg, log=False)
    return root / "recommendation"


def test_build_popular_outputs(rec_dir):
    assert (rec_dir / "popular_model.joblib").exists()
    assert (rec_dir / "popular_items.csv").exists()
    assert (rec_dir / "popular_recommendations.csv").exists()

    meta = json.loads((rec_dir / "recommendation_meta.json").read_text(encoding="utf-8"))
    assert meta["algorithm"] == "popular"
    assert meta["task"] == "popular_baseline"
    assert "score_formula" in meta
    assert meta["time_decay"]["half_life_days"] == 7
    assert meta["stats"]["n_items_scored"] >= 1
    assert meta["stats"]["n_recommendations"] >= 1
    assert meta["filtering"]["off_shelf"] is True

    items = pd.read_csv(rec_dir / "popular_items.csv", encoding="utf-8-sig")
    assert items["score"].between(0, 1).all()

    model = joblib.load(rec_dir / "popular_model.joblib")
    recs = model.recommend("U000001", top_k=5)
    assert len(recs) <= 5
    if recs:
        assert set(recs[0].keys()) >= {"item_id", "score", "reason"}
        assert all(r["score"] >= 0 for r in recs)


def test_meta_records_config(rec_dir):
    meta = json.loads((rec_dir / "recommendation_meta.json").read_text(encoding="utf-8"))
    assert set(meta["behavior_components"].keys()) == {"pv", "click", "collect", "cart", "buy"}
    assert meta["behavior_components"]["buy"]["weight"] == 5.0
    assert meta["config"]["top_k"] == 5