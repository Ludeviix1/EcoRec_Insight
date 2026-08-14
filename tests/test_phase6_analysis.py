"""Phase 6 留存 + Cohort + RFM 测试（开发文档第 49.4 节）。

覆盖：
- Cohort：首次活跃为起点，day_0/day_1/... 口径与计数正确；register 起点；
- 留存：次日 / 3日 / 7日 / 14日 / 30日整体留存率；
- RFM：R/F/M 定义、1~5 评分、RFM_score、分群可解释；
- RFM 分数规则可配置（自定义分桶 / 分群规则）；
- end-to-end：ETL 产物 -> 分析 -> 输出 retention/cohort/rfm JSON。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.analysis.cohort import cohort_analysis
from analysis.analysis.config import load_analysis_config
from analysis.analysis.retention import retention_analysis
from analysis.analysis.rfm import RfmConfig, rfm_analysis
from analysis.analysis.run import run_analysis
from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl
from test_phase5_analysis import _behaviors

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


# ---------------------------------------------------------------------
# 一、Cohort
# ---------------------------------------------------------------------
def test_cohort_analysis_first_behavior():
    beh = _behaviors()
    out = cohort_analysis(beh)
    assert out["cohort_base"] == "first_behavior"
    assert out["offsets"][0] == 0
    # 首次活跃日：U1/U2/U3 分别在 08-03 / 08-04 / 08-05
    dates = {r["cohort_date"] for r in out["cohorts"]}
    assert dates == {"2026-08-03", "2026-08-04", "2026-08-05"}
    sizes = {r["cohort_date"]: r["day_0"] for r in out["cohorts"]}
    assert sizes["2026-08-03"] == 1   # U1
    assert sizes["2026-08-04"] == 1
    assert sizes["2026-08-05"] == 1
    # 留存率在 [0,1]
    for r in out["cohorts"]:
        for d in (1, 3, 7, 14, 30):
            assert 0.0 <= r[f"rate_day_{d}"] <= 1.0
    assert out["total_users"] == 3


def test_cohort_analysis_register():
    beh = _behaviors()
    users = pd.DataFrame({
        "user_id": ["U1", "U2", "U3"],
        "register_time": ["2026-08-03", "2026-08-02", "2026-08-01"],
    })
    out = cohort_analysis(beh, users, cohort_base="register")
    assert out["cohort_base"] == "register"
    dates = {r["cohort_date"] for r in out["cohorts"]}
    assert dates == {"2026-08-01", "2026-08-02", "2026-08-03"}
    with pytest.raises(ValueError):
        cohort_analysis(beh, cohort_base="register")          # 缺 users
    with pytest.raises(ValueError):
        cohort_analysis(beh, cohort_base="unknown")           # 非法起点


# ---------------------------------------------------------------------
# 二、留存
# ---------------------------------------------------------------------
def test_retention_analysis():
    out = retention_analysis(_behaviors())
    offsets = [o["offset"] for o in out["overall"]]
    assert offsets == [1, 3, 7, 14, 30]
    labels = {o["label"] for o in out["overall"]}
    assert labels == {"次日", "3日", "7日", "14日", "30日"}
    for o in out["overall"]:
        assert 0.0 <= o["rate"] <= 1.0
        assert o["base"] == 3      # 3 个 cohort 各 1 人
    # 数据只有 08-03..08-05 三天，day_1 应有人 —— 但所有 cohort 之间相差 1 天，
    # 例如 08-03 用户在 08-04 无行为，因此次日留存率不会全部为 1。
    assert all(o["retained"] >= 0 for o in out["overall"])
    assert out["definition"]        # 口径说明非空


# ---------------------------------------------------------------------
# 三、RFM
# ---------------------------------------------------------------------
def _rfm_orders() -> pd.DataFrame:
    """确定性 RFM 订单表（时间精确到日，as_of 取 2026-08-07）。

    - U1：近 90 天 4 笔 paid，金额 4000 -> 高价值；
    - U2：近 90 天 1 笔 paid（O6 cancelled 不计）-> 潜力；
    - U3：07-01 购买（recency 37 天）-> 流失风险兜底。
    """
    return pd.DataFrame({
        "order_id": ["O1", "O2", "O3", "O4", "O5", "O6", "O7"],
        "user_id": ["U1", "U1", "U1", "U1", "U2", "U2", "U3"],
        "order_time": ["2026-08-01", "2026-08-03", "2026-08-05", "2026-08-06",
                       "2026-08-01", "2026-08-02", "2026-07-01"],
        "total_amount": [1000.0, 1000.0, 1000.0, 1000.0, 500.0, 0.0, 300.0],
        "status": ["paid", "paid", "paid", "paid", "paid", "cancelled", "paid"],
        "payment_method": ["balance"] * 7,
    })


def test_rfm_analysis_default():
    out = rfm_analysis(_rfm_orders(), RfmConfig(as_of_date="2026-08-07"))
    assert out["total_buying_users"] == 3          # U3 也有 paid
    assert out["definition"]["period_days"] == 90
    assert out["scoring"]["r_bins"] == [30, 60, 90, 120]

    users = {u["user_id"]: u for u in out["users"]}
    assert set(users) == {"U1", "U2", "U3"}
    for u in users.values():
        assert 1 <= u["r_score"] <= 5
        assert 1 <= u["f_score"] <= 5
        assert 1 <= u["m_score"] <= 5
        assert u["rfm_score"] == u["r_score"] * 100 + u["f_score"] * 10 + u["m_score"]
        assert u["segment"] in {"高价值", "重要保持", "潜力", "一般", "沉睡", "流失风险"}
    # U1：recency=1（08-06 购买, as_of 08-07）-> R=5；F=4 -> 4；M=4000 -> 4
    u1 = users["U1"]
    assert u1["recency_days"] == 1
    assert u1["r_score"] == 5
    assert u1["f_score"] == 4
    assert u1["m_score"] == 4
    assert u1["segment"] == "高价值"
    # U2：recency=6 -> R=5；F=1 -> 2；M=500 -> 2 -> 潜力
    assert users["U2"]["r_score"] == 5
    assert users["U2"]["f_score"] == 2
    assert users["U2"]["segment"] == "潜力"
    # U3：recency=37 -> R=4；M=300 -> 1 -> 流失风险
    assert users["U3"]["r_score"] == 4
    assert users["U3"]["m_score"] == 1
    assert users["U3"]["segment"] == "流失风险"


def test_rfm_scoring_configurable():
    """自定义分桶与分群规则应生效。"""
    orders = _rfm_orders()
    cfg = RfmConfig(
        as_of_date="2026-08-07",
        period_days=90,
        r_bins=(1, 2, 3, 4),
        f_bins=(10, 20, 30, 40),
        m_bins=(10_000, 20_000, 30_000, 40_000),
        segment_rules=({"segment": "测试高价值", "r_min": 4, "f_min": 4, "m_min": 4},
                       {"segment": "兜底"}),
    )
    out = rfm_analysis(orders, cfg)
    assert out["scoring"]["r_bins"] == [1, 2, 3, 4]
    users = {u["user_id"]: u for u in out["users"]}
    # U1 recency=1 -> 不 <1 但 <2 -> 4 分；U3 recency=37 -> 1 分
    assert users["U1"]["r_score"] == 4
    assert users["U3"]["r_score"] == 1
    # F/M 分桶都很大，全为 1 分
    assert users["U1"]["f_score"] == 1
    assert users["U1"]["m_score"] == 1
    # 分群使用自定义规则
    segments = {u["segment"] for u in out["users"]}
    assert segments <= {"测试高价值", "兜底"}


def test_rfm_segment_interpretable():
    """分群结果可解释：高价值用户 F/M 更优。"""
    out = rfm_analysis(_rfm_orders(), RfmConfig(as_of_date="2026-08-07"))
    seg = {s["segment"]: s for s in out["segment_distribution"]}
    assert "高价值" in seg
    # 高价值 = U1（4000），潜力 = U2（500），流失风险 = U3（300）
    assert seg["高价值"]["gmv"] == pytest.approx(4000.0)
    assert seg["高价值"]["count"] == 1
    all_gmv = sum(s["gmv"] for s in out["segment_distribution"])
    assert all_gmv == pytest.approx(4800.0)


# ---------------------------------------------------------------------
# 四、end-to-end
# ---------------------------------------------------------------------
@pytest.fixture(scope="module")
def phase6_dir(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("phase6")
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


def test_run_analysis_produces_phase6_outputs(phase6_dir):
    for name in ("retention", "cohort", "rfm", "analysis_meta"):
        assert (phase6_dir / f"{name}.json").exists()

    meta = json.loads((phase6_dir / "analysis_meta.json").read_text(encoding="utf-8"))
    assert "retention" in meta["results"]
    assert "cohort" in meta["results"]
    assert "rfm" in meta["results"]

    retention = json.loads((phase6_dir / "retention.json").read_text(encoding="utf-8"))
    assert len(retention["overall"]) == 5
    assert all(0.0 <= o["rate"] <= 1.0 for o in retention["overall"])

    cohort = json.loads((phase6_dir / "cohort.json").read_text(encoding="utf-8"))
    assert cohort["total_cohorts"] >= 1
    assert {"day_0", "day_1", "day_30"} <= set(cohort["cohorts"][0].keys())

    rfm = json.loads((phase6_dir / "rfm.json").read_text(encoding="utf-8"))
    assert rfm["total_buying_users"] >= 1
    assert all(u["segment"] for u in rfm["users"])