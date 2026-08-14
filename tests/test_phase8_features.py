"""Phase 8 特征工程测试（开发文档第 49.6 节）。

覆盖：
- 观察窗口：只使用窗口内数据，窗口外行为/订单不计入；
- 用户级特征：行为计数 / 转化率 / 活跃 / 会话 / RFM 类 / 购买聚合；
- 商品级特征：行为计数 / GMV（仅 paid）/ 转化率 / 热度分；
- 用户-商品交互特征：按对计数 / is_bought / 时间偏移；
- 防泄漏：不产生任何 label / future / next 列；
- 数据字典：覆盖全部输出列；
- 可复现：同配置两次计算完全一致；
- end-to-end：生成 -> ETL -> 特征工程 -> 三张 CSV + 字典 + meta。
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
from analysis.feature_engineering.base import observation_window
from analysis.feature_engineering.config import FeatureConfig, load_feature_config
from analysis.feature_engineering.dictionary import feature_dictionary
from analysis.feature_engineering.item_features import build_item_features
from analysis.feature_engineering.run import run_feature_engineering
from analysis.feature_engineering.user_features import build_user_features
from analysis.feature_engineering.user_item_features import build_user_item_features

# 观察窗口：30 天，结束 2026-08-31 => [2026-08-02, 2026-08-31]
OBS_END = "2026-08-31"
OBS_DAYS = 30
_CFG = FeatureConfig(obs_end=OBS_END, observation_days=OBS_DAYS, session_gap_minutes=30)

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


# ---------------------------------------------------------------------
# 构造测试数据
# ---------------------------------------------------------------------
def _behaviors() -> pd.DataFrame:
    """行为表：U1 窗口内 3 行为+2 个窗口外行为；U2/U3 窗口内；U4 无行为。"""
    return pd.DataFrame({
        "behavior_id": ["B1", "B2", "B3", "B4", "B5",
                        "B6", "B7",
                        "B8"],
        "user_id": ["U1", "U1", "U1", "U1", "U1",
                    "U2", "U2",
                    "U3"],
        "item_id": ["I1", "I1", "I1", "I1", "I1",
                    "I1", "I1",
                    "I1"],
        "behavior_type": ["pv", "pv", "click", "buy", "pv",
                          "pv", "pv",
                          "buy"],
        "event_time": ["2026-07-01 10:00:00", "2026-08-05 10:00:00", "2026-08-05 10:05:00",
                       "2026-08-20 10:00:00", "2026-09-01 10:00:00",
                       "2026-08-10 10:00:00", "2026-08-11 10:00:00",
                       "2026-08-25 10:00:00"],
        "event_date": ["2026-07-01", "2026-08-05", "2026-08-05",
                       "2026-08-20", "2026-09-01",
                       "2026-08-10", "2026-08-11",
                       "2026-08-25"],
        "event_hour": [10, 10, 10, 10, 10, 10, 10, 10],
        "device_type": ["pc", "mobile", "pc", "mobile", "pc",
                        "mobile", "tablet",
                        "mobile"],
        "channel": ["organic"] * 8,
    })


def _users() -> pd.DataFrame:
    return pd.DataFrame({
        "user_id": ["U1", "U2", "U3", "U4"],
        "age": [25.0, 30.0, 35.0, 40.0],
        "gender": ["M", "F", "M", "F"],
        "city": ["北京", "上海", "广州", "深圳"],
        "register_time": ["2026-01-01", "2026-01-02", "2026-08-15", "2026-01-03"],
        "created_at": ["2026-01-01"] * 4,
        "updated_at": ["2026-01-01"] * 4,
    })


def _items() -> pd.DataFrame:
    return pd.DataFrame({
        "item_id": ["I1", "I2", "I3"],
        "item_name": ["手机A", "手机B", "耳机C"],
        "category_id": ["C01", "C02", "C02"],
        "brand": ["华为", "小米", "华为"],
        "price": [3999.0, 2999.0, 199.0],
        "stock": [100.0, 200.0, 300.0],
        "status": [1, 1, 1],
        "created_at": ["2026-01-01", "2026-08-10", "2026-01-01"],
    })


def _orders() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1", "O2", "O3", "O4", "O5"],
        "user_id": ["U1", "U2", "U2", "U1", "U3"],
        "order_time": ["2026-08-21 10:00:00", "2026-08-09 10:00:00", "2026-08-28 10:00:00",
                       "2026-07-01 10:00:00", "2026-08-30 10:00:00"],
        "total_amount": [100.0, 50.0, 999.0, 500.0, 200.0],
        "status": ["paid", "paid", "cancelled", "paid", "paid"],
        "payment_method": ["balance"] * 5,
    })


def _order_items() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1", "O2", "O4", "O5"],
        "item_id": ["I1", "I1", "I1", "I1"],
        "quantity": [1, 1, 1, 2],
        "unit_price": [100.0, 50.0, 500.0, 100.0],
        "amount": [100.0, 50.0, 500.0, 200.0],
    })


# ---------------------------------------------------------------------
# 一、观察窗口与防泄漏
# ---------------------------------------------------------------------
def test_observation_window_range():
    start, end = _window_range()
    assert str(end.date()) == OBS_END
    assert (end - start).days == OBS_DAYS - 1   # 闭区间长度为 observation_days 天


def _window_range():
    return observation_window(_CFG, _behaviors())


def test_observation_end_default_from_data():
    """obs_end 与 etl_meta anchor 都缺失时取行为数据最大日期。"""
    cfg = FeatureConfig(observation_days=30, interim_dir=Path("__no_such_dir__"))
    start, end = observation_window(cfg, _behaviors())
    assert str(end.date()) == "2026-09-01"


def test_user_features_observation_window_only():
    """窗口外行为（07-01、09-01）与窗口外订单（O4）不计入。"""
    out = build_user_features(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    u1 = out[out["user_id"] == "U1"].iloc[0]
    assert u1["total_behaviors"] == 3          # B2 pv + B3 click + B4 buy
    assert u1["n_pv"] == 1                      # 窗口外 B1/B5 不算
    assert u1["n_click"] == 1
    assert u1["n_buy"] == 1
    assert u1["n_active_days"] == 2             # 08-05, 08-20
    assert u1["recency_days"] == 11             # 08-31 - 08-20
    assert u1["first_activity_offset_days"] == 3  # 08-05 - 08-02
    assert u1["n_sessions"] == 2                # 08-05 与 08-20 间隔 > 30min
    assert u1["paid_order_count"] == 1          # O4(07-01) 窗口外不算
    assert u1["paid_gmv"] == 100.0
    assert u1["purchased_items"] == 1
    assert u1["has_purchase"] == 1


def test_user_features_no_behavior_defaults():
    out = build_user_features(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    u4 = out[out["user_id"] == "U4"].iloc[0]
    assert u4["total_behaviors"] == 0
    assert u4["recency_days"] == OBS_DAYS
    assert u4["first_activity_offset_days"] == 0
    assert u4["top_channel"] == ""
    assert u4["has_purchase"] == 0
    assert u4["paid_gmv"] == 0.0
    assert 0.0 <= u4["active_day_ratio"] <= 1.0


def test_user_features_ratios():
    out = build_user_features(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    u1 = out[out["user_id"] == "U1"].iloc[0]
    assert u1["behavior_buy_ratio"] == pytest.approx(1 / 3, abs=5e-4)   # round 到 4 位小数
    assert u1["buy_rate"] == pytest.approx(1.0)       # n_buy / n_pv = 1/1
    assert u1["click_rate"] == pytest.approx(1.0)
    assert u1["behaviors_per_session"] == pytest.approx(1.5)
    assert u1["avg_order_amount"] == pytest.approx(100.0)
    u3 = out[out["user_id"] == "U3"].iloc[0]
    assert u3["buy_rate"] == 0.0                      # 无 pv -> safe_div=0
    assert u3["is_new_in_window"] == 1                # 注册 08-15 在窗口内
    assert u3["paid_gmv"] == 200.0


def test_no_label_or_future_columns():
    out = build_user_features(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    for col in out.columns:
        assert "label" not in col.lower()
        assert "future" not in col.lower()
        assert "next" not in col.lower()


# ---------------------------------------------------------------------
# 二、商品级特征
# ---------------------------------------------------------------------
def test_item_features():
    out = build_item_features(_items(), _behaviors(), _order_items(), _orders(), _CFG)
    i1 = out[out["item_id"] == "I1"].iloc[0]
    assert i1["n_pv"] == 3               # B2(U1)+B6/B7(U2) 在窗口内；B1/B5 不算
    assert i1["n_click"] == 1
    assert i1["n_buy"] == 2              # B4(U1) + B8(U3)
    assert i1["total_behaviors"] == 6
    assert i1["n_unique_users"] == 3
    assert i1["gmv"] == pytest.approx(350.0)   # O1(100)+O2(50)+O5(200)；O4(500)窗口外不算
    assert i1["units_sold"] == 4
    assert i1["n_paid_orders"] == 3
    assert i1["conversion_rate"] == pytest.approx(2 / 3, abs=5e-4)   # buy/pv = 2/3
    assert i1["heat_score"] > 0
    # 窗口内无任何行为/销售的商品：全 0，last_behavior_offset=observation_days
    i3 = out[out["item_id"] == "I3"].iloc[0]
    assert i3["total_behaviors"] == 0
    assert i3["gmv"] == 0.0
    assert i3["last_behavior_offset_days"] == OBS_DAYS
    assert i3["conversion_rate"] == 0.0


# ---------------------------------------------------------------------
# 三、用户-商品交互特征
# ---------------------------------------------------------------------
def test_user_item_features():
    out = build_user_item_features(_behaviors(), _items(), _CFG)
    assert {"U1", "U2", "U3"} == set(out["user_id"])
    u1 = out[(out["user_id"] == "U1") & (out["item_id"] == "I1")].iloc[0]
    assert u1["n_pv"] == 1
    assert u1["n_click"] == 1
    assert u1["n_buy"] == 1
    assert u1["total_behaviors"] == 3
    assert u1["is_bought"] == 1
    assert u1["category_id"] == "C01"
    assert u1["days_since_last"] == 11
    assert u1["weighted_score"] == 1 + 2 + 5      # pv:1 + click:2 + buy:5
    u2 = out[(out["user_id"] == "U2") & (out["item_id"] == "I1")].iloc[0]
    assert u2["n_pv"] == 2
    assert u2["is_bought"] == 0
    # U4 无行为 -> 不出现在交互表中
    assert "U4" not in set(out["user_id"])


def test_user_item_weight_configurable():
    cfg = FeatureConfig(obs_end=OBS_END, observation_days=OBS_DAYS,
                        behavior_weights={"pv": 1, "click": 2, "collect": 4, "cart": 6, "buy": 10})
    out = build_user_item_features(_behaviors(), _items(), cfg)
    u1 = out[(out["user_id"] == "U1") & (out["item_id"] == "I1")].iloc[0]
    assert u1["weighted_score"] == 1 + 2 + 10     # pv:1 + click:2 + buy:10


# ---------------------------------------------------------------------
# 四、数据字典覆盖全部列
# ---------------------------------------------------------------------
def test_dictionary_covers_all_columns():
    entries = feature_dictionary()
    by_table: dict[str, set[str]] = {}
    for e in entries:
        by_table.setdefault(e["table"], set()).add(e["field"])
    # 每个字典条目都有说明
    for e in entries:
        assert e["field"] and e["description"] and e["data_type"] and e["window"]

    user_f = build_user_features(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    item_f = build_item_features(_items(), _behaviors(), _order_items(), _orders(), _CFG)
    uitem_f = build_user_item_features(_behaviors(), _items(), _CFG)
    for df, table in ((user_f, "user_features"), (item_f, "item_features"), (uitem_f, "user_item_features")):
        missing = set(df.columns) - by_table.get(table, set())
        assert not missing, f"{table} 缺少字典字段: {missing}"
        extra = by_table.get(table, set()) - set(df.columns)
        assert not extra, f"{table} 字典存在但无对应列: {extra}"


# ---------------------------------------------------------------------
# 五、可复现
# ---------------------------------------------------------------------
def test_reproducible():
    a = build_user_features(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    b = build_user_features(_users(), _behaviors(), _orders(), _order_items(), _items(), _CFG)
    pd.testing.assert_frame_equal(a, b)


# ---------------------------------------------------------------------
# 六、end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def feature_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase8")
    raw = root / "raw"
    gen_cfg = load_config(output_dir=str(raw), **TEST_GEN)
    run_generation(gen_cfg, log=False)

    etl_cfg = load_etl_config(
        raw_dir=str(raw),
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        mysql=False,
        chunk_size=1000,
    )
    run_etl(etl_cfg, log=False)

    fcfg = load_feature_config(
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        output_dir=str(root / "features"),
        observation_days=30,
    )
    run_feature_engineering(fcfg, log=False)
    return root / "features"


def test_run_feature_engineering_outputs(feature_dir):
    for name in ("user_features", "item_features", "user_item_features"):
        assert (feature_dir / f"{name}.csv").exists()

    meta = json.loads((feature_dir / "feature_meta.json").read_text(encoding="utf-8"))
    assert meta["feature_version"]
    assert meta["observation_window_days"] == 30
    assert meta["feature_time_range"]["end"] > meta["feature_time_range"]["start"]
    assert meta["leakage_guard"]
    assert set(meta["results"]) == {"user_features", "item_features", "user_item_features"}

    # 行数校验：用户特征 = 全部用户；交互表行数 > 0
    users = pd.read_csv(meta["tables"]["user_features"]["path"], encoding="utf-8-sig")
    assert len(users) == 200
    uitem = pd.read_csv(meta["tables"]["user_item_features"]["path"], encoding="utf-8-sig")
    assert len(uitem) > 0

    # 字典覆盖实际 CSV 全部列
    entries = feature_dictionary()
    by_table = {}
    for e in entries:
        by_table.setdefault(e["table"], set()).add(e["field"])
    for table, info in meta["tables"].items():
        df = pd.read_csv(info["path"], encoding="utf-8-sig")
        missing = set(df.columns) - by_table[table]
        assert not missing, f"{table} 缺少字典字段: {missing}"


def test_feature_time_range_spans_observation_days(feature_dir):
    meta = json.loads((feature_dir / "feature_meta.json").read_text(encoding="utf-8"))
    start = pd.Timestamp(meta["feature_time_range"]["start"])
    end = pd.Timestamp(meta["feature_time_range"]["end"])
    assert (end - start).days == meta["observation_window_days"] - 1