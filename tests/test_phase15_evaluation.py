"""Phase 15 推荐评估测试（开发文档第 49.13 节 / 36 节）。

覆盖：
- 严格时间切分：历史 → train，未来 → test，推荐只用 train 信息；
- 5 种算法（Popular / ItemCF / UserCF / Content / Hybrid）对比；
- 指标列：Precision@10 / Recall@10 / F1@10 / HitRate@10 / NDCG@10 / Coverage；
- 结论必须基于评估指标：Hybrid 未优于 Popular 时禁止声称 Hybrid 更好；
- `run_evaluation.py` 规范化输出（evaluation_summary.csv / .json）。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import pandas as pd
import pytest

from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl
from analysis.feature_engineering.base import load_processed
from analysis.recommendation.config import load_recommend_config
from analysis.recommendation.evaluate import (
    conclude_vs_baseline,
    report_table,
    split_train_test,
)
from scripts.run_evaluation import main as run_evaluation_main

TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=4000)


@pytest.fixture(scope="module")
def _cfg():
    return load_recommend_config(hybrid_weights={"itemcf": 0.25, "usercf": 0.15,
                                                 "popular": 0.30, "content": 0.30})


@pytest.fixture(scope="module")
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("phase15")
    raw = root / "raw"
    run_generation(replace(load_config(output_dir=str(raw)), **TEST_GEN), log=False)
    etl_cfg = load_etl_config(
        raw_dir=str(raw),
        processed_dir=str(root / "processed"),
        interim_dir=str(root / "interim"),
        mysql=False,
        chunk_size=1000,
    )
    run_etl(etl_cfg, log=False)
    return root


@pytest.fixture()
def behaviors(data_root):
    return load_processed(data_root / "processed", "user_behaviors")


def test_split_train_test_strict_time_cut(behaviors, _cfg):
    """严格时间切分：train 全部发生在 cut_date 之前（<=），test 全部在其后。"""
    train, test, cut = split_train_test(behaviors, test_ratio=0.25)
    tr_max = pd.to_datetime(train["event_date"]).max()
    te_min = pd.to_datetime(test["event_date"]).min()
    assert tr_max <= cut < te_min
    assert len(train) > 0 and len(test) > 0
    # test 只用于评价：切分日期的存在不允许把 test 信息泄漏进 train
    assert pd.to_datetime(train["event_date"]).max() < te_min


def test_report_table_has_spec_columns():
    """Phase 15 输出列：Algorithm / Precision@10 / Recall@10 / F1@10 / HitRate@10 / NDCG@10 / Coverage。"""
    summary = pd.DataFrame({
        "algorithm": ["popular", "hybrid"],
        "precision@k": [0.1, 0.2], "recall@k": [0.1, 0.2], "f1@k": [0.1, 0.2],
        "hit_rate@k": [0.5, 0.6], "ndcg@k": [0.3, 0.4], "coverage@k": [0.9, 0.8],
        "n_users": [10, 10], "rank": [2, 1],
    })
    tbl = report_table(summary, k=10)
    assert list(tbl.columns) == ["Algorithm", "Precision@10", "Recall@10", "F1@10",
                                 "HitRate@10", "NDCG@10", "Coverage"]
    assert tbl["Algorithm"].tolist() == ["popular", "hybrid"]
    assert len(tbl) == 2


def test_conclude_honest_when_hybrid_not_better():
    """Hybrid 未高于 Popular 时，结论禁止声称 Hybrid 更好（第 49.13 节）。"""
    details = {
        "popular": {"precision@k": 0.05, "recall@k": 0.06, "ndcg@k": 0.0047},
        "itemcf": {"precision@k": 0.05, "recall@k": 0.06, "ndcg@k": 0.0030},
        "usercf": {"precision@k": 0.05, "recall@k": 0.06, "ndcg@k": 0.0035},
        "content": {"precision@k": 0.05, "recall@k": 0.06, "ndcg@k": 0.0040},
        "hybrid": {"precision@k": 0.05, "recall@k": 0.06, "ndcg@k": 0.0040},
    }
    concl = conclude_vs_baseline(details, k=10, baseline="popular")
    assert "不强行声称混合更好" in concl
    assert "更优" not in concl


def test_conclude_claims_only_when_strictly_better():
    """Hybrid 严格高于 baseline 时才声称更优。"""
    details = {
        "popular": {"ndcg@k": 0.0047},
        "hybrid": {"ndcg@k": 0.0085},
    }
    concl = conclude_vs_baseline(details, k=10, baseline="popular")
    assert "更优（基于离线指标）" in concl
    assert "不强行声称混合更好" not in concl


def test_evaluation_script_outputs(data_root, _cfg):
    """run_evaluation.py e2e：产出规范化 summary（csv/json）与诚实结论。"""
    processed = data_root / "processed"
    interim = data_root / "interim"
    out = data_root / "recommendation"
    out.mkdir(parents=True, exist_ok=True)

    rc = run_evaluation_main([
        "--processed-dir", str(processed),
        "--interim-dir", str(interim),
        "--output-dir", str(out),
        "--k", "10", "--test-ratio", "0.25", "--max-users", "100",
    ])
    assert rc == 0
    assert (out / "evaluation_summary.csv").exists()
    assert (out / "evaluation_summary.json").exists()
    df = pd.read_csv(out / "evaluation_summary.csv")
    assert list(df.columns) == ["Algorithm", "Precision@10", "Recall@10", "F1@10",
                                "HitRate@10", "NDCG@10", "Coverage"]
    assert len(df) == 5
    doc = json.loads((out / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert set(doc["results"].keys()) == {"popular", "itemcf", "usercf", "content", "hybrid"}
    # 结论必然出现在 JSON 里
    assert "conclusion" in doc