"""Phase 5 基础分析测试（开发文档第 49.3 节）。

覆盖：
- 用户规模：总用户 / 活跃 / 购买 / 付费率；
- DAU / WAU / MAU 定义与趋势；
- 行为分析：PV/Click/Collect/Cart/Buy 计数与转化率；
- 活跃时间：hour / weekday / device 分布；
- GMV / 订单 / 客单价 / ARPU；
- 商品排行 / 分类排行 / 品牌排行；
- 转化漏斗：step / overall 转化率；
- 安全除法（防除零）；
- end-to-end：ETL 产物 -> 基础分析 -> 输出 JSON。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.analysis.base import safe_div
from analysis.analysis.config import load_analysis_config
from analysis.analysis.funnel import conversion_funnel
from analysis.analysis.gmv import gmv_analysis
from analysis.analysis.item import brand_ranking, category_ranking, item_ranking
from analysis.analysis.run import run_analysis
from analysis.analysis.user import active_time, behavior_analysis, dau_wau_mau, user_scale
from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl

# 测试用小规模数据
TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


# ---------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------
def _behaviors() -> pd.DataFrame:
    """构造一张行为表：3 个用户，包含全部 5 种行为。"""
    return pd.DataFrame({
        "behavior_id": [f"B{i}" for i in range(12)],
        "user_id": ["U1", "U1", "U1", "U1", "U1",
                    "U2", "U2", "U2", "U2",
                    "U3", "U1", "U3"],
        "item_id": ["I1"] * 12,
        "behavior_type": ["pv", "pv", "pv", "click", "click",
                          "click", "collect", "cart", "cart",
                          "buy", "pv", "pv"],
        "event_time": pd.date_range("2026-08-01", periods=12, freq="h").astype(str),
        "event_date": ["2026-08-03", "2026-08-03", "2026-08-03", "2026-08-03", "2026-08-03",
                       "2026-08-04", "2026-08-04", "2026-08-04", "2026-08-04",
                       "2026-08-05", "2026-08-05", "2026-08-05"],
        "event_hour": [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
        "device_type": ["mobile", "mobile", "pc", "pc", "pc",
                        "mobile", "tablet", "tablet", "mobile",
                        "mobile", "pc", "mobile"],
        "channel": ["organic"] * 12,
    })


def _users() -> pd.DataFrame:
    return pd.DataFrame({
        "user_id": ["U1", "U2", "U3", "U4"],
        "age": [25, 30, 35, 40],
        "gender": ["M", "F", "M", "F"],
        "city": ["北京", "上海", "广州", "深圳"],
        "register_time": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-03"],
        "created_at": ["2026-01-01"] * 4,
        "updated_at": ["2026-01-01"] * 4,
    })


def _items() -> pd.DataFrame:
    return pd.DataFrame({
        "item_id": ["I1", "I2", "I3"],
        "item_name": ["手机A", "手机B", "耳机C"],
        "category_id": ["C01", "C01", "C02"],
        "brand": ["华为", "小米", "华为"],
        "price": [3999, 2999, 199],
        "stock": [100, 200, 300],
        "status": [1, 1, 1],
        "created_at": ["2026-01-01"] * 3,
    })


def _orders() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1", "O2", "O3", "O4"],
        "user_id": ["U1", "U2", "U3", "U4"],
        "order_time": ["2026-08-01 10:00:00", "2026-08-01 11:00:00",
                       "2026-08-02 12:00:00", "2026-08-03 13:00:00"],
        "total_amount": [3999.0, 2999.0, 199.0, 0.0],
        "status": ["paid", "paid", "paid", "cancelled"],
        "payment_method": ["balance", "balance", "wechat", "balance"],
    })


def _order_items() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1", "O2", "O3"],
        "item_id": ["I1", "I2", "I3"],
        "quantity": [1, 1, 1],
        "unit_price": [3999.0, 2999.0, 199.0],
        "amount": [3999.0, 2999.0, 199.0],
    })


# ---------------------------------------------------------------------
# 一、安全除法
# ---------------------------------------------------------------------
def test_safe_div():
    assert safe_div(10, 2) == 5.0
    assert safe_div(10, 0) == 0.0
    assert safe_div(None, 2) == 0.0
    assert safe_div(10, None) == 0.0
    assert safe_div("a", 2) == 0.0
    assert safe_div(1, 3) == 0.3333


# ---------------------------------------------------------------------
# 二、用户规模
# ---------------------------------------------------------------------
def test_user_scale():
    users, beh = _users(), _behaviors()
    out = user_scale(users, beh)
    assert out["total_users"] == 4
    assert out["new_users"] == 4
    assert out["active_users"] == 3          # U4 无行为
    assert out["buying_users"] == 1          # 仅 U3 有 buy
    assert out["pay_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert len(out["register_trend"]) == 3   # 三个注册日期
    assert out["gender_distribution"]        # 非空
    assert out["city_distribution"]


# ---------------------------------------------------------------------
# 三、DAU / WAU / MAU
# ---------------------------------------------------------------------
def test_dau_wau_mau():
    out = dau_wau_mau(_behaviors())
    # DAU：8/03 有 U1；8/04 有 U2；8/05 有 U1、U3
    dau = {r["date"]: r["value"] for r in out["dau"]}
    assert dau["2026-08-03"] == 1
    assert dau["2026-08-04"] == 1
    assert dau["2026-08-05"] == 2
    # WAU/MAU：同一周/月内去重用户 = {U1, U2, U3}
    assert out["latest_wau"] == 3
    assert out["latest_mau"] == 3
    # 趋势列表按时间升序
    dates = [r["date"] for r in out["dau"]]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------
# 四、行为分析
# ---------------------------------------------------------------------
def test_behavior_analysis():
    out = behavior_analysis(_behaviors())
    assert out["total"] == 12
    assert out["counts"]["pv"] == 5
    assert out["counts"]["click"] == 3
    assert out["counts"]["collect"] == 1
    assert out["counts"]["cart"] == 2
    assert out["counts"]["buy"] == 1
    assert out["rates"]["click_rate"] == pytest.approx(3 / 5)
    assert out["rates"]["buy_rate"] == pytest.approx(1 / 5)
    # 日趋势包含三个日期，且每日有全部 5 种行为键
    days = {r["date"] for r in out["daily_trend"]}
    assert days == {"2026-08-03", "2026-08-04", "2026-08-05"}
    assert set(out["daily_trend"][0].keys()) >= {"pv", "click", "collect", "cart", "buy"}


# ---------------------------------------------------------------------
# 五、活跃时间
# ---------------------------------------------------------------------
def test_active_time():
    out = active_time(_behaviors())
    assert len(out["by_hour"]) == 24
    total = sum(r["total"] for r in out["by_hour"])
    assert total == 12
    assert sum(r["count"] for r in out["by_weekday"]) == 12
    # 设备分布：mobile/pc/tablet 各 24 个 hour 桶
    assert {d["device"] for d in out["by_device_hour"]} == {"mobile", "pc", "tablet"}
    assert all(len(d["hours"]) == 24 for d in out["by_device_hour"])


# ---------------------------------------------------------------------
# 六、GMV / 客单价 / ARPU
# ---------------------------------------------------------------------
def test_gmv_analysis():
    orders = _orders()
    out = gmv_analysis(orders, _behaviors())
    # GMV 只统计 paid：O1 + O2 + O3 = 7197；O4 cancelled 不计
    assert out["gmv_total"] == pytest.approx(7197.0)
    assert out["order_count"] == 3
    assert out["buying_users"] == 3
    assert out["aov"] == pytest.approx(7197.0 / 3)
    assert out["arpu"] == pytest.approx(7197.0 / 3, abs=0.001)  # active_users=3
    assert out["status_distribution"]["paid"] == 3
    assert out["status_distribution"]["cancelled"] == 1
    # 日趋势：8/01 有 2 单，8/02 有 1 单
    daily = {r["date"]: r for r in out["daily_trend"]}
    assert daily["2026-08-01"]["orders"] == 2
    assert daily["2026-08-02"]["orders"] == 1
    assert out["monthly_trend"]


# ---------------------------------------------------------------------
# 七、商品 / 分类 / 品牌排行
# ---------------------------------------------------------------------
def test_item_ranking():
    out = item_ranking(_items(), _behaviors(), _order_items(), _orders(), top_n=3)
    assert out["total"] == 3
    ids = [r["item_id"] for r in out["items"]]
    assert set(ids) == {"I1", "I2", "I3"}
    first = out["items"][0]
    assert set(first.keys()) >= {"item_id", "gmv", "pv", "click", "collect", "cart",
                                 "buy", "unique_users", "conversion_rate", "heat_score"}
    # I1 有 gmv=3999 且行为最多 -> 应排第一
    assert first["item_id"] == "I1"
    assert first["gmv"] == pytest.approx(3999.0)


def test_category_ranking():
    out = category_ranking(_items(), _behaviors(), _order_items(), _orders(), top_n=2)
    cats = {r["category_id"] for r in out["categories"]}
    assert "C01" in cats and "C02" in cats
    c01 = next(r for r in out["categories"] if r["category_id"] == "C01")
    assert c01["gmv"] == pytest.approx(6998.0)   # I1+I2 paid 明细
    assert c01["conversion_rate"] >= 0


def test_brand_ranking():
    out = brand_ranking(_items(), _behaviors(), _order_items(), _orders(), top_n=2)
    brands = {r["brand"] for r in out["brands"]}
    assert "华为" in brands and "小米" in brands
    huawei = next(r for r in out["brands"] if r["brand"] == "华为")
    assert huawei["gmv"] == pytest.approx(4198.0)  # I1(3999)+I3(199)
    assert huawei["buy_users"] == 2                 # I1、I3 各被 U1、U3 购买


# ---------------------------------------------------------------------
# 八、转化漏斗
# ---------------------------------------------------------------------
def test_conversion_funnel():
    out = conversion_funnel(_behaviors())
    steps = {s["stage"]: s for s in out["steps"]}
    assert out["stages"] == ["pv", "click", "collect", "cart", "buy"]
    assert steps["pv"]["count"] == 5
    assert steps["buy"]["count"] == 1
    assert steps["pv"]["step_conversion_rate"] == 1.0
    assert steps["click"]["step_conversion_rate"] == pytest.approx(3 / 5)
    assert steps["buy"]["overall_conversion_rate"] == pytest.approx(1 / 5)
    # 漏斗计数单调不增（该测试数据：pv=5 > click=3 > collect=1，但 cart=2 允许回弹，
    # 仅验证 buy <= pv）
    assert steps["buy"]["count"] <= steps["pv"]["count"]


# ---------------------------------------------------------------------
# 九、end-to-end：生成 -> ETL -> 基础分析
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def analysis_dir(tmp_path_factory) -> Path:
    """小规模数据：生成 -> ETL(无 MySQL) -> 基础分析，返回 analysis 输出目录。"""
    root = tmp_path_factory.mktemp("phase5")
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

    out_dir = root / "analysis"
    acfg = load_analysis_config(
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        output_dir=str(out_dir),
        top_n=5,
    )
    run_analysis(acfg, log=False)
    return out_dir


def test_run_analysis_produces_all_outputs(analysis_dir):
    expected = {
        "user_scale", "dau_wau_mau", "behavior", "active_time", "gmv",
        "item_ranking", "category_ranking", "brand_ranking", "funnel",
        "retention", "cohort", "rfm",
        "lifecycle", "purchase_path", "item_lifecycle", "price",
        "channel", "device", "association", "user_segments",
        "user_profile", "item_profile", "findings",
        "analysis_meta",
    }
    files = {p.stem for p in analysis_dir.glob("*.json")}
    assert expected <= files

    meta = json.loads((analysis_dir / "analysis_meta.json").read_text(encoding="utf-8"))
    assert meta["results"] == [
        "user_scale", "dau_wau_mau", "behavior", "active_time", "gmv",
        "item_ranking", "category_ranking", "brand_ranking", "funnel",
        "retention", "cohort", "rfm",
        "lifecycle", "purchase_path", "item_lifecycle", "price",
        "channel", "device", "association", "user_segments",
        "user_profile", "item_profile", "findings",
    ]

    # 抽查结构：funnel 5 阶段
    funnel = json.loads((analysis_dir / "funnel.json").read_text(encoding="utf-8"))
    assert len(funnel["steps"]) == 5
    assert funnel["steps"][-1]["stage"] == "buy"

    # 行为计数与生成期 meta 一致
    behavior = json.loads((analysis_dir / "behavior.json").read_text(encoding="utf-8"))
    assert behavior["total"] > 0
    assert behavior["counts"]["pv"] > behavior["counts"]["buy"] >= 0
