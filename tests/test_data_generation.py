"""Phase 3 数据生成测试（开发文档第 45 节：数据 -- 数据量 / 空值 / 重复 / 外键一致性）。

覆盖：
- 数据量与可配置性
- 完整性（关键字段非空）、唯一性（ID 不重复）、一致性（外键引用合法）
- 合法性（行为/设备/渠道/状态取值集合）、时间约束（不早于注册、不晚于截止日）
- 行为-订单一致性（buy 行为数 == order_items 数；订单金额 == 明细之和）
- 漏斗单调递减
- 业务规律（价值分层 / 热度分层 / 偏好分类 / 渠道差异 / 价格分布 / 时间规律）
- 可复现性（同种子同输出）
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.data_generation import generators
from analysis.data_generation.config import RANDOM_STATE, load_config
from analysis.data_generation.generate import run_generation

# 测试用小规模配置，保证测试秒级完成
TEST_CFG = dict(n_users=400, n_items=200, n_behaviors=6000)


# ---------------------------------------------------------------------
# session 级共享数据：生成一次，多测试复用
# ---------------------------------------------------------------------
@pytest.fixture(scope="session")
def gen_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("raw")
    cfg = load_config(output_dir=str(d), **TEST_CFG)
    run_generation(cfg, log=False)
    return d


@pytest.fixture(scope="session")
def dfs(gen_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "categories": pd.read_csv(gen_dir / "categories.csv"),
        "users": pd.read_csv(gen_dir / "users.csv"),
        "items": pd.read_csv(gen_dir / "items.csv"),
        "behaviors": pd.read_csv(gen_dir / "user_behaviors.csv"),
        "orders": pd.read_csv(gen_dir / "orders.csv"),
        "order_items": pd.read_csv(gen_dir / "order_items.csv"),
    }


# =====================================================================
# 一、数据量与可配置性
# =====================================================================
def test_data_volume(dfs):
    """各表行数符合配置预期；行为量近似命中目标。"""
    assert len(dfs["users"]) == TEST_CFG["n_users"]
    assert len(dfs["items"]) == TEST_CFG["n_items"]
    # 行为数应在目标 ±50% 内（行为链展开为近似）
    assert 0.5 * TEST_CFG["n_behaviors"] <= len(dfs["behaviors"]) <= 1.5 * TEST_CFG["n_behaviors"]
    assert len(dfs["orders"]) > 0
    assert len(dfs["order_items"]) > 0


def test_config_scale_presets():
    """规模预设 low/standard/large 可加载且数值递增。"""
    low = load_config(scale="low")
    std = load_config(scale="standard")
    large = load_config(scale="large")
    assert low.n_users < std.n_users
    assert std.n_behaviors < large.n_behaviors


def test_meta_file_written(gen_dir: Path):
    """data_meta.json 存在且记录种子 / 数据版本 / 各表行数。"""
    meta = json.loads((gen_dir / "data_meta.json").read_text(encoding="utf-8"))
    assert meta["random_state"] == RANDOM_STATE
    assert meta["schema_version"]
    for key in ("users", "items", "user_behaviors", "orders", "order_items"):
        assert key in meta["counts"] and meta["counts"][key] > 0
    assert "data_end_date" in meta


# =====================================================================
# 二、完整性（非空）
# =====================================================================
def test_no_nulls_critical(dfs):
    """user_id / item_id / event_time 等关键字段无空值。"""
    assert dfs["behaviors"][["user_id", "item_id", "event_time"]].isna().sum().sum() == 0
    assert dfs["users"]["user_id"].isna().sum() == 0
    assert dfs["items"]["item_id"].isna().sum() == 0
    assert dfs["orders"]["order_id"].isna().sum() == 0


# =====================================================================
# 三、唯一性（ID 不重复）
# =====================================================================
def test_no_duplicate_ids(dfs):
    """behavior_id / order_id / user_id / item_id 全局唯一。"""
    assert dfs["behaviors"]["behavior_id"].is_unique
    assert dfs["orders"]["order_id"].is_unique
    assert dfs["users"]["user_id"].is_unique
    assert dfs["items"]["item_id"].is_unique


# =====================================================================
# 四、一致性（外键引用合法）
# =====================================================================
def test_fk_consistency(dfs):
    """行为/订单/明细引用的 user_id / item_id / order_id 均存在。"""
    users = set(dfs["users"]["user_id"])
    items = set(dfs["items"]["item_id"])
    orders = set(dfs["orders"]["order_id"])

    assert dfs["behaviors"]["user_id"].isin(users).all()
    assert dfs["behaviors"]["item_id"].isin(items).all()
    assert dfs["orders"]["user_id"].isin(users).all()
    assert dfs["order_items"]["order_id"].isin(orders).all()
    assert dfs["order_items"]["item_id"].isin(items).all()


def test_category_parent_consistency(dfs):
    """分类的 parent_id 要么为空（一级），要么指向已存在的 category_id。"""
    cat = dfs["categories"]
    cat_ids = set(cat["category_id"])
    parents = cat["parent_id"].dropna()
    assert parents.isin(cat_ids).all()
    # 一级分类数量 = 10（开发文档第 7 节）
    assert int(cat["parent_id"].isna().sum()) == 10


# =====================================================================
# 五、合法性（取值集合）
# =====================================================================
def test_value_sets(dfs):
    """behavior_type / device / channel / order status 取值合法。"""
    assert set(dfs["behaviors"]["behavior_type"]) <= {"pv", "click", "collect", "cart", "buy"}
    assert set(dfs["behaviors"]["behavior_type"]) == {"pv", "click", "collect", "cart", "buy"}
    assert set(dfs["behaviors"]["device_type"]) <= {"mobile", "pc", "tablet"}
    assert set(dfs["behaviors"]["channel"]) <= {"organic", "search", "ads", "campaign", "recommendation"}
    assert set(dfs["orders"]["status"]) <= {"paid", "cancelled", "refunded"}


def test_event_date_hour_redundant_columns(dfs):
    """event_date / event_hour 与 event_time 一致（冗余列加速查询，需正确）。"""
    beh = dfs["behaviors"]
    ev = pd.to_datetime(beh["event_time"])
    assert (beh["event_hour"].astype(int) == ev.dt.hour).all()
    assert (beh["event_date"] == ev.dt.strftime("%Y-%m-%d")).all()


# =====================================================================
# 六、时间约束
# =====================================================================
def test_time_constraints(dfs):
    """事件时间不早于注册时间；事件/订单时间不晚于数据截止日（2026-08-31）。"""
    reg = dfs["users"].set_index("user_id")["register_time"].apply(pd.to_datetime)
    beh_time = pd.to_datetime(dfs["behaviors"]["event_time"])
    beh_reg = dfs["behaviors"]["user_id"].map(reg)
    assert (beh_time >= beh_reg).all(), "存在行为时间早于用户注册时间"

    end = pd.Timestamp("2026-08-31 23:59:59")
    assert (beh_time <= end).all(), "存在行为时间晚于数据截止日"

    order_time = pd.to_datetime(dfs["orders"]["order_time"])
    order_reg = dfs["orders"]["user_id"].map(reg)
    assert (order_time >= order_reg).all()
    assert (order_time <= end).all()


# =====================================================================
# 七、行为-订单一致性
# =====================================================================
def test_buy_equals_order_items(dfs):
    """每条 buy 行为对应一条 order_item（含 cancelled/refunded 订单）。"""
    n_buy = int((dfs["behaviors"]["behavior_type"] == "buy").sum())
    assert n_buy == len(dfs["order_items"])


def test_order_total_matches_items(dfs):
    """订单 total_amount == 其明细 amount 之和。"""
    merged = dfs["order_items"].groupby("order_id")["amount"].sum()
    totals = dfs["orders"].set_index("order_id")["total_amount"]
    cmp = merged.reindex(totals.index).fillna(0).round(2)
    assert (cmp == totals.round(2)).all()


def test_order_items_amount_correct(dfs):
    """order_item.amount == quantity * unit_price。"""
    oi = dfs["order_items"]
    assert (oi["quantity"] > 0).all()
    assert (oi["unit_price"] >= 0).all()
    assert ((oi["quantity"] * oi["unit_price"]).round(2) == oi["amount"].round(2)).all()


# =====================================================================
# 八、漏斗单调递减（开发文档第 19 节）
# =====================================================================
def test_funnel_monotonic(dfs):
    """PV >= Click >= Collect >= Cart >= Buy。"""
    c = dfs["behaviors"]["behavior_type"].value_counts()
    assert c["pv"] >= c["click"] >= c["collect"] >= c["cart"] >= c["buy"]


# =====================================================================
# 九、业务规律（开发文档第 13 节）
# =====================================================================
def test_value_tier_distribution():
    """高/中/低价值用户占比：low > medium > high。"""
    rng = np.random.default_rng(RANDOM_STATE)
    cfg = load_config(n_users=3000)
    users = generators.generate_users(rng, cfg)
    vc = users["value_tier"].value_counts()
    assert vc["low"] > vc["medium"] > vc["high"]
    # 偏好分类数量 1~3
    assert users["preferred_categories"].apply(len).between(1, 3).all()


def test_heat_level_distribution():
    """商品热度分层：normal 最多，cold 次之，hot 最少（按目录占比）。"""
    rng = np.random.default_rng(RANDOM_STATE)
    cfg = load_config(n_items=2000)
    cats = generators.generate_categories(rng, cfg)
    items = generators.generate_items(rng, cfg, cats)
    vc = items["heat_level"].value_counts()
    assert vc["normal"] > vc["cold"] > vc["hot"]


def test_channel_conversion_differs(dfs):
    """不同渠道的购买转化率（buy/click）存在明显差异 -> 渠道分析有意义。"""
    ch = dfs["behaviors"].groupby("channel")["behavior_type"].value_counts().unstack(fill_value=0)
    buy_per_click = (ch["buy"] / ch["click"].replace(0, np.nan)).dropna()
    # 最大渠道转化率应明显高于最小渠道（差异 > 3 个百分点）
    assert (buy_per_click.max() - buy_per_click.min()) > 0.03


def test_price_differs_by_category(dfs):
    """不同一级分类的价格中位数差异显著（数码/电脑贵，食品/图书便宜）。"""
    items = dfs["items"].merge(dfs["categories"][["category_id", "parent_id"]], on="category_id")
    cat = dfs["categories"]
    top_name = cat.set_index("category_id")["category_name"].to_dict()
    items["top"] = items["parent_id"].map(top_name)
    med = items.groupby("top")["price"].median()
    # 手机数码 / 电脑办公 的中位数应远高于 食品 / 图书
    assert med.get("手机数码", 0) > med.get("食品", 0) * 10
    assert med.get("电脑办公", 0) > med.get("图书", 0) * 10


def test_evening_more_active(dfs):
    """晚间（18~23 点）活跃度高于凌晨（0~6 点）。"""
    hour_counts = dfs["behaviors"]["event_hour"].value_counts()
    evening = hour_counts.reindex(range(18, 24), fill_value=0).sum()
    midnight = hour_counts.reindex(range(0, 6), fill_value=0).sum()
    assert evening > midnight


def test_items_have_brands_and_categories(dfs):
    """商品均属于某个分类且有品牌；至少 10 个一级分类下有商品。"""
    assert dfs["items"]["category_id"].notna().all()
    assert dfs["items"]["brand"].notna().all()
    items = dfs["items"].merge(dfs["categories"][["category_id", "parent_id"]], on="category_id")
    top = dfs["categories"].set_index("category_id")["category_name"].to_dict()
    items["top"] = items["parent_id"].map(top)
    assert items["top"].nunique() == 10


def test_orders_include_multi_item(tmp_path):
    """存在多商品同单订单（供关联规则挖掘，开发文档第 26 节）。"""
    cfg = load_config(n_users=1000, n_items=500, n_behaviors=20000, output_dir=str(tmp_path))
    run_generation(cfg, log=False)
    oi = pd.read_csv(tmp_path / "order_items.csv")
    counts = oi.groupby("order_id").size()
    assert counts.max() >= 2, "缺少多商品订单，关联规则将无信号"


# =====================================================================
# 十、可复现性（开发文档第 47 节：random_state=42）
# =====================================================================
def test_reproducibility(tmp_path_factory):
    """相同种子生成两次，user_behaviors.csv 内容完全一致。"""
    d1 = tmp_path_factory.mktemp("r1")
    d2 = tmp_path_factory.mktemp("r2")
    run_generation(load_config(n_users=200, n_items=100, n_behaviors=2000, output_dir=str(d1)), log=False)
    run_generation(load_config(n_users=200, n_items=100, n_behaviors=2000, output_dir=str(d2)), log=False)
    assert (d1 / "user_behaviors.csv").read_text(encoding="utf-8-sig") == \
           (d2 / "user_behaviors.csv").read_text(encoding="utf-8-sig")
