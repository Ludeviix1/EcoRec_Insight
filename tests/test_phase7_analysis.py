"""Phase 7 深度业务分析测试（开发文档第 49.5 节）。

覆盖：
- 生命周期：默认规则（高价值/新用户/成长期/活跃/沉默/流失风险）、规则可配置；
- 购买路径：会话切分、路径压缩、最终购买率、不含 search；
- 商品生命周期：阶段判定含新品/成长/爆款/成熟/衰退/无购买；
- 价格：自动分箱、费率、GMV、价格-转化相关性在 [-1,1]；
- 渠道：指标齐全、非 ROI 声明；
- 设备：mobile/pc/tablet 指标；
- 关联规则：item/category 两级、support/confidence/lift；
- 用户分群：KMeans cluster_id/cluster_name/业务解释；
- 用户画像 / 商品画像：字段完整；
- 业务发现：现象→证据→可能原因→业务建议 + 模拟数据声明；
- end-to-end：ETL -> 全量分析 -> 输出全部 Phase 7 JSON。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.analysis.association import AssociationConfig, association_analysis
from analysis.analysis.channel import channel_analysis, device_analysis
from analysis.analysis.config import load_analysis_config
from analysis.analysis.findings import build_findings
from analysis.analysis.itemlife import ItemLifeConfig, item_lifecycle_analysis
from analysis.analysis.lifecycle import LifecycleConfig, lifecycle_analysis
from analysis.analysis.path import PathConfig, purchase_path_analysis
from analysis.analysis.price import PriceConfig, price_analysis
from analysis.analysis.profile import item_profile, user_profile
from analysis.analysis.run import run_analysis
from analysis.analysis.segmentation import SegmentConfig, user_segmentation
from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl
from test_phase5_analysis import _behaviors, _items, _order_items, _orders, _users

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


# ---------------------------------------------------------------------
# 一、生命周期
# ---------------------------------------------------------------------
def test_lifecycle_analysis():
    out = lifecycle_analysis(_users(), _behaviors(), _orders())
    assert out["total_users"] == 4
    dist = {s["stage"]: s for s in out["distribution"]}
    # 所有用户都在某个阶段
    assert sum(s["count"] for s in out["distribution"]) == 4
    # 默认规则存在兜底
    assert out["config"]["rules"][-1]["stage"] == "流失风险"
    users = {u["user_id"]: u for u in out["users"]}
    assert set(users) == {"U1", "U2", "U3", "U4"}
    for u in users.values():
        assert u["stage"] in {"高价值用户", "新用户", "成长期", "活跃用户", "沉默用户", "流失风险"}


def test_lifecycle_configurable():
    """自定义规则：全部归为新用户。"""
    cfg = LifecycleConfig(rules=({"stage": "测试用户"},))
    out = lifecycle_analysis(_users(), _behaviors(), _orders(), cfg)
    assert {u["stage"] for u in out["users"]} == {"测试用户"}
    assert out["distribution"][0]["count"] == 4


# ---------------------------------------------------------------------
# 二、购买路径
# ---------------------------------------------------------------------
def test_purchase_path_analysis():
    beh = _behaviors()
    out = purchase_path_analysis(beh)
    assert out["total_sessions"] >= 1
    assert out["distinct_paths"] >= 1
    assert out["definition"]  # 口径说明
    # 数据只有 5 种行为，不应出现 search
    for p in out["top_paths"]:
        assert "search" not in p["path"]
        for token in p["path"].split("→"):
            assert token in {"pv", "click", "collect", "cart", "buy"}
    # 有最终购买路径存在（_behaviors 含 buy）
    assert any(p["buy_sessions"] > 0 for p in out["top_paths"])


def test_purchase_path_session_split():
    """相邻间隔 > gap 切分会话：同一用户间隔超过阈值算新会话。"""
    beh = pd.DataFrame({
        "behavior_id": ["B1", "B2"],
        "user_id": ["U1", "U1"],
        "item_id": ["I1", "I1"],
        "behavior_type": ["pv", "pv"],
        "event_time": ["2026-08-01 10:00:00", "2026-08-01 10:30:00"],
        "event_date": ["2026-08-01", "2026-08-01"],
        "event_hour": [10, 10],
        "device_type": ["mobile", "mobile"],
        "channel": ["organic", "organic"],
    })
    out = purchase_path_analysis(beh, PathConfig(session_gap_minutes=60))
    assert out["total_sessions"] == 1          # 间隔 30 分钟 <= 60 -> 同一会话
    out2 = purchase_path_analysis(beh, PathConfig(session_gap_minutes=20))
    assert out2["total_sessions"] == 2         # 间隔 30 分钟 > 20 -> 两个会话


# ---------------------------------------------------------------------
# 三、商品生命周期
# ---------------------------------------------------------------------
def test_item_lifecycle_analysis():
    items = pd.DataFrame({
        "item_id": ["I1", "I2", "I3", "I4"],
        "item_name": ["新品", "老品", "热品", "无购"],
        "category_id": ["C01", "C01", "C01", "C01"],
        "brand": ["A", "B", "C", "D"],
        "price": [100, 200, 300, 400],
        "stock": [100] * 4,
        "status": [1] * 4,
        "created_at": ["2026-07-20", "2026-01-01", "2026-01-01", "2026-01-01"],
    })
    beh = _behaviors().copy()
    # 让 I3 有较多购买，I4 无行为
    extra = pd.DataFrame({
        "behavior_id": [f"E{i}" for i in range(20)],
        "user_id": ["U1"] * 20,
        "item_id": ["I3"] * 20,
        "behavior_type": ["buy"] * 20,
        "event_time": pd.date_range("2026-08-10", periods=20, freq="h").astype(str),
        "event_date": ["2026-08-10"] * 20,
        "event_hour": [12] * 20,
        "device_type": ["mobile"] * 20,
        "channel": ["organic"] * 20,
    })
    beh = pd.concat([beh, extra], ignore_index=True)
    oi = pd.DataFrame({"order_id": [f"X{i}" for i in range(20)],
                       "item_id": ["I3"] * 20,
                       "quantity": [1] * 20,
                       "unit_price": [300] * 20,
                       "amount": [300] * 20})
    orders = pd.DataFrame({"order_id": [f"X{i}" for i in range(20)],
                           "user_id": ["U1"] * 20,
                           "order_time": pd.date_range("2026-08-10", periods=20, freq="h").astype(str),
                           "total_amount": [300] * 20,
                           "status": ["paid"] * 20,
                           "payment_method": ["balance"] * 20})
    out = item_lifecycle_analysis(items, beh, oi, orders)
    assert out["total_items"] == 4
    stages = {i["item_id"]: i["stage"] for i in out["items"]}
    assert stages["I1"] == "新品"      # 创建距今 <= 30 天
    assert stages["I4"] == "无购买"     # 无购买
    assert all(0.0 <= s["ratio"] <= 1.0 for s in out["distribution"])


# ---------------------------------------------------------------------
# 四、价格分析
# ---------------------------------------------------------------------
def test_price_analysis():
    out = price_analysis(_items(), _behaviors(), _order_items(), _orders())
    assert out["total_price_bins"] >= 1
    for b in out["price_bins"]:
        assert b["price_max"] > b["price_min"]
        assert 0.0 <= b["buy_rate"] <= 1.0
    # 相关性在合法范围
    for k, v in out["cross"].items():
        assert -1.0 <= v["correlation"] <= 1.0


# ---------------------------------------------------------------------
# 五、渠道 / 设备
# ---------------------------------------------------------------------
def test_channel_analysis():
    out = channel_analysis(_users(), _behaviors(), _orders())
    assert len(out["channels"]) == 5
    for c in out["channels"]:
        assert c["channel"] in {"organic", "search", "ads", "campaign", "recommendation"}
        assert c["users"] >= 0
        assert 0.0 <= c["buy_rate"] <= 1.0
    assert "渠道质量对比" in out["note"]
    assert "不声称真实 ROI" in out["note"] or "非 ROI" in out["note"] or "不声称" in out["note"]


def test_device_analysis():
    out = device_analysis(_users(), _behaviors(), _orders())
    devs = {d["device"] for d in out["devices"]}
    assert devs <= {"mobile", "pc", "tablet"}
    for d in out["devices"]:
        assert 0.0 <= d["buy_rate"] <= 1.0
        assert 0.0 <= d["evening_ratio"] <= 1.0


# ---------------------------------------------------------------------
# 六、关联规则
# ---------------------------------------------------------------------
def test_association_analysis():
    oi = pd.DataFrame({
        "order_id": ["O1", "O1", "O2", "O2", "O3", "O3", "O4"],
        "item_id": ["I1", "I2", "I1", "I2", "I1", "I2", "I3"],
    })
    orders = pd.DataFrame({
        "order_id": ["O1", "O2", "O3", "O4"],
        "user_id": ["U1", "U1", "U1", "U1"],
        "order_time": ["2026-08-01"] * 4,
        "total_amount": [100, 100, 100, 50],
        "status": ["paid"] * 4,
        "payment_method": ["balance"] * 4,
    })
    items = _items()
    out = association_analysis(oi, orders, items,
                               AssociationConfig(min_support=0.5, min_confidence=0.5, min_lift=0.5))
    assert out["total_orders"] == 4
    # I1+I2 在 3 单中同时出现 -> 应有商品级规则
    assert out["item_rules_count"] >= 1
    for r in out["item_rules"]:
        assert 0.0 <= r["support"] <= 1.0
        assert 0.0 <= r["confidence"] <= 1.0
        assert r["lift"] >= 0


# ---------------------------------------------------------------------
# 七、用户分群
# ---------------------------------------------------------------------
def test_user_segmentation():
    out = user_segmentation(_behaviors(), _orders(), SegmentConfig(n_clusters=3))
    assert out["n_clusters"] == 3
    assert len(out["clusters"]) == 3
    total_size = sum(c["size"] for c in out["clusters"])
    assert total_size == out["users"].__len__() if out["users"] else True
    for c in out["clusters"]:
        assert c["cluster_name"]
        assert c["interpretation"]
        assert set(c["feature_means"].keys()) == set(out["features"])
    # users 都能找到对应 cluster_name
    names = {c["cluster_name"] for c in out["clusters"]}
    assert all(u["cluster_name"] in names for u in out["users"])


# ---------------------------------------------------------------------
# 八、用户画像 / 商品画像
# ---------------------------------------------------------------------
def test_user_profile():
    out = user_profile(_users(), _behaviors(), _orders(), _order_items(), _items())
    assert out["total_users"] == 4
    first = out["profiles"][0]
    for key in ("user_id", "basic", "behavior", "purchase", "spending_power",
                "active_time", "preferred_categories", "preferred_brands",
                "lifecycle_stage", "rfm", "channel", "device"):
        assert key in first
    assert "lifecycle_stage" in first and first["lifecycle_stage"] is not None


def test_item_profile():
    out = item_profile(_items(), _behaviors(), _order_items(), _orders())
    assert out["total_items"] == 3
    first = out["profiles"][0]
    for key in ("item_id", "item_name", "basic", "behavior", "sales",
                "lifecycle_stage", "price_band", "heat_score"):
        assert key in first


# ---------------------------------------------------------------------
# 九、业务发现
# ---------------------------------------------------------------------
def test_findings_structure():
    results = {
        "user_scale": {"total_users": 100, "active_users": 80, "pay_rate": 0.5},
        "funnel": {"steps": [{"stage": "pv", "count": 100, "step_conversion_rate": 1.0},
                             {"stage": "click", "count": 60, "step_conversion_rate": 0.6},
                             {"stage": "buy", "count": 10, "step_conversion_rate": 0.1667}]},
        "retention": {"overall": [{"label": "次日", "rate": 0.18, "retained": 18, "base": 100}]},
        "cohort": {"total_cohorts": 5, "aggregate": {"day_1": 0.18, "day_7": 0.14, "day_30": 0.12}},
        "rfm": {"segment_distribution": [{"segment": "高价值", "count": 10, "gmv": 5000},
                                          {"segment": "流失风险", "count": 20, "gmv": 300}]},
        "lifecycle": {"distribution": [{"stage": "活跃用户", "count": 50, "ratio": 0.5, "gmv": 4000},
                                        {"stage": "流失风险", "count": 10, "ratio": 0.1, "gmv": 100}]},
        "purchase_path": {"top_paths": [{"path": "pv→click→buy", "sessions": 5, "users": 3,
                                          "final_buy_rate": 1.0}]},
        "item_ranking": {"items": [{"item_name": "手机A", "pv": 100, "buy": 5, "gmv": 5000}]},
        "item_lifecycle": {"distribution": [{"stage": "爆款", "count": 2, "total_gmv": 8000},
                                              {"stage": "新品", "count": 3, "total_gmv": 500}]},
        "price": {"price_bins": [{"bin_label": "高价", "buy_rate": 0.05, "gmv": 5000}],
                  "cross": {"price_vs_buy_rate": {"correlation": -0.3}}},
        "channel": {"channels": [{"channel": "search", "users": 50, "buy_rate": 0.1,
                                   "gmv": 4000, "aov": 100}], "note": "渠道质量对比"},
        "device": {"devices": [{"device": "mobile", "users": 80, "buy_rate": 0.09,
                                 "gmv": 8000, "behavior_ratio": 0.7, "evening_ratio": 0.45}]},
        "association": {"item_rules_count": 1, "category_rules_count": 1,
                        "config": {"min_support": 0.001},
                        "item_rules": [{"antecedents": ["手机A"], "consequents": ["手机壳"],
                                        "support": 0.01, "confidence": 0.3, "lift": 2.0}],
                        "category_rules": []},
        "user_segments": {"clusters": [{"cluster_id": 0, "cluster_name": "高价值活跃",
                                         "size": 30, "ratio": 0.3,
                                         "interpretation": "消费高"}]},
    }
    out = build_findings(results)
    assert out["disclaimer"]  # 模拟数据声明
    assert out["total_domains"] == len(results)
    for d in out["domains"]:
        assert d["domain"] and d["title"]
        for f in d["findings"]:
            assert set(f.keys()) == {"现象", "证据", "可能原因", "业务建议"}
            assert f["证据"]
    # 数据为模拟数据，不得表述为真实业务结论
    assert "模拟数据" in out["disclaimer"]


# ---------------------------------------------------------------------
# 十、end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def phase7_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase7")
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


def test_run_analysis_produces_phase7_outputs(phase7_dir):
    expected = {
        "lifecycle", "purchase_path", "item_lifecycle", "price",
        "channel", "device", "association", "user_segments",
        "user_profile", "item_profile", "findings",
    }
    files = {p.stem for p in phase7_dir.glob("*.json")}
    assert expected <= files

    meta = json.loads((phase7_dir / "analysis_meta.json").read_text(encoding="utf-8"))
    assert all(k in meta["results"] for k in expected)

    # 抽查结构
    lifecycle = json.loads((phase7_dir / "lifecycle.json").read_text(encoding="utf-8"))
    assert lifecycle["total_users"] > 0
    assert sum(s["count"] for s in lifecycle["distribution"]) == lifecycle["total_users"]

    path = json.loads((phase7_dir / "purchase_path.json").read_text(encoding="utf-8"))
    assert path["total_sessions"] > 0

    seg = json.loads((phase7_dir / "user_segments.json").read_text(encoding="utf-8"))
    assert len(seg["clusters"]) == seg["n_clusters"] > 0
    assert all(c["cluster_name"] for c in seg["clusters"])

    findings = json.loads((phase7_dir / "findings.json").read_text(encoding="utf-8"))
    assert "模拟数据" in findings["disclaimer"]
    assert findings["total_domains"] >= 10