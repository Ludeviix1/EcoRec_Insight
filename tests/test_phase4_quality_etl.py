"""Phase 4 数据质量 + ETL 测试（开发文档第 49.2 节 / 第 14 节 / 第 15 节）。

覆盖：
- 清洗：完整性 / 合法性 / 唯一性 / 冗余列重建 / 整值列收敛
- 质检：一致性（逻辑外键）/ 时间（不早于注册、不晚于截止日）/ 跨分片唯一性
- ETL：全链路产出 processed CSV + 质检报告 + 运行记录；end-to-end 能识别脏数据
- 幂等：重复执行不产生重复订单/行为；MySQL 重复加载行数不变
- 大文件：chunk_size 分片读取/写入（开发文档第 15 节）
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.cleaning import clean_chunk, validate_header
from analysis.data_generation.config import load_config
from analysis.data_generation.generate import run_generation
from analysis.etl.config import load_etl_config
from analysis.etl.pipeline import run_etl
from analysis.etl.specs import TABLE_SPECS
from analysis.quality import QualityChecker, build_context

# 测试用小规模配置
TEST_GEN = dict(n_users=200, n_items=100, n_behaviors=3000)


def _mysql_available() -> bool:
    try:
        import pymysql

        cfg = load_etl_config()
        conn = pymysql.connect(host=cfg.mysql_host, port=cfg.mysql_port,
                               user=cfg.mysql_user, password=cfg.mysql_password,
                               connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


MYSQL_OK = _mysql_available()
require_mysql = pytest.mark.skipif(not MYSQL_OK, reason="MySQL 服务不可用，跳过入库测试")


# ---------------------------------------------------------------------
# fixture：生成一次小数据集（供 ETL 与质检测试复用）
# ---------------------------------------------------------------------
@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("raw")
    cfg = load_config(output_dir=str(d), **TEST_GEN)
    run_generation(cfg, log=False)
    return d


@pytest.fixture(scope="session")
def etl_cfg(tmp_path_factory, request) -> object:
    d = tmp_path_factory.mktemp("etl_out")
    cfg = load_etl_config(
        raw_dir=str(request.getfixturevalue("raw_dir")),
        processed_dir=str(d / "processed"),
        interim_dir=str(d / "interim"),
        mysql=False,
        chunk_size=1000,  # 强制小批量，验证分片路径
    )
    return cfg


# =====================================================================
# 一、清洗单元测试
# =====================================================================
def test_clean_drops_duplicates_and_nulls():
    spec = TABLE_SPECS["users"]
    df = pd.DataFrame({
        "user_id": ["U1", "U1", None, "U2", "U2", "U3"],
        "age": [30, 25, 22, None, 20, 28],
        "gender": ["M", "M", "F", "F", "M", "F"],
        "city": ["北京", "上海", "广州", "深圳", None, "杭州"],
        "register_time": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "bad"],
        "created_at": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"],
        "updated_at": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"],
    })
    kept, stats = clean_chunk(df, spec)
    # 丢弃：user_id=None(1) + U1 副本(1) + U2 副本(1) + 非法注册时间(1)
    assert kept["user_id"].tolist() == ["U1", "U2"]
    assert stats["missing"] == 1        # 仅 user_id=None 的行
    assert stats["duplicates"] == 2     # U1 / U2 重复副本
    assert stats["illegal"] >= 1        # register_time 解析失败
    assert stats["kept"] == len(kept)


def test_clean_allowed_values_and_bounds():
    spec = TABLE_SPECS["items"]
    df = pd.DataFrame({
        "item_id": ["I1", "I2", "I3"],
        "item_name": ["a", "b", "c"],
        "category_id": ["C1", "C1", "C1"],
        "brand": ["x", "y", "z"],
        "price": [10.5, -1.0, 20.0],     # 第二个价格为负 -> 越界
        "stock": [100, 5, -3],           # 第三个库存为负 -> 越界
        "status": [1, 2, 0],             # status=2 非法
        "created_at": ["2026-01-01", "2026-01-02", "2026-01-03"],
    })
    kept, stats = clean_chunk(df, spec)
    # I2 价格越界、I3 库存越界、I2 状态非法 -> 仅 I1 保留
    assert kept["item_id"].tolist() == ["I1"]
    assert stats["illegal"] == 2


def test_clean_recomputes_redundant_columns():
    spec = TABLE_SPECS["user_behaviors"]
    df = pd.DataFrame({
        "behavior_id": ["B1"],
        "user_id": ["U1"],
        "item_id": ["I1"],
        "behavior_type": ["click"],
        "event_time": ["2026-08-04 19:45:30"],
        "event_date": ["2026-01-01"],        # 故意错误
        "event_hour": [1],                   # 故意错误
        "device_type": ["mobile"],
        "channel": ["organic"],
    })
    kept, stats = clean_chunk(df, spec)
    assert stats["illegal"] == 0
    assert kept.iloc[0]["event_date"] == "2026-08-04"
    assert int(kept.iloc[0]["event_hour"]) == 19


def test_validate_header_detects_missing_columns():
    spec = TABLE_SPECS["users"]
    bad = pd.Index(["user_id", "age", "city"])
    missing = validate_header(bad, spec)
    assert "register_time" in missing and "gender" in missing


# =====================================================================
# 二、质检单元测试（一致性 / 时间 / 全局唯一）
# =====================================================================
def test_quality_consistency_and_time():
    spec = TABLE_SPECS["user_behaviors"]
    ctx = build_context(
        user_ids=["U1", "U2"],
        item_ids=["I1"],
        category_ids=[],
        order_ids=[],
        register_time={"U1": pd.Timestamp("2026-08-01")},
        data_end=pd.Timestamp("2026-08-31 23:59:59"),
    )
    checker = QualityChecker(ctx)
    df = pd.DataFrame({
        "behavior_id": ["B1", "B2", "B3", "B4"],
        "user_id": ["U1", "U9", "U2", "U1"],     # U9 不存在
        "item_id": ["I1", "I1", "I9", "I1"],     # I9 不存在
        "behavior_type": ["pv", "pv", "pv", "pv"],
        "event_time": ["2026-08-10", "2026-08-10", "2026-08-10", "2026-07-01"],  # 最后行为早于注册
        "event_date": ["2026-08-10"] * 4,
        "event_hour": [10] * 4,
        "device_type": ["mobile"] * 4,
        "channel": ["organic"] * 4,
    })
    fk_mask, fk_detail = checker.consistency(df, spec)
    assert int(fk_mask.sum()) == 2
    assert fk_detail.get("item_id") == 1 and fk_detail.get("user_id") == 1

    t_mask, t_detail = checker.time(df, spec)
    assert int(t_mask.sum()) == 1
    assert t_detail.get("event_time<register") == 1


def test_quality_global_unique_across_chunks():
    """跨分片唯一性：seen 集合累积后，后续分片中的重复 key 应被识别。"""
    spec = TABLE_SPECS["user_behaviors"]
    checker = QualityChecker(build_context(
        user_ids=[], item_ids=[], category_ids=[], order_ids=[], register_time={}, data_end=None))
    df = pd.DataFrame({
        "behavior_id": ["B1", "B2"],
        "user_id": ["U1", "U1"],
        "item_id": ["I1", "I1"],
        "behavior_type": ["pv", "pv"],
        "event_time": ["2026-08-01", "2026-08-02"],
        "event_date": ["2026-08-01", "2026-08-02"],
        "event_hour": [1, 2],
        "device_type": ["mobile"] * 2,
        "channel": ["organic"] * 2,
    })
    seen: set = set()
    # 分片一：全部为新 key，无重复
    _, n1 = checker.global_duplicates(df, spec, seen)
    assert n1 == 0
    # 分片二：与分片一重合 -> 全部被判重
    _, n2 = checker.global_duplicates(df, spec, seen)
    assert n2 == 2
    # 分片三：混合新旧 key
    df3 = df.assign(behavior_id=["B1", "B3"])
    _, n3 = checker.global_duplicates(df3, spec, seen)
    assert n3 == 1


# =====================================================================
# 三、ETL 全链路（无 MySQL）
# =====================================================================
def test_etl_produces_processed_and_reports(raw_dir, etl_cfg):
    meta = run_etl(etl_cfg, log=False)
    assert meta["dataset_version"] == "v1"
    assert meta["etl_version"] == "1.0"
    assert meta["generator_version"]  # 复用 Phase 3 生成期 meta

    # processed 六表 + 报告 + 运行记录
    for name in ("categories", "users", "items", "user_behaviors", "orders", "order_items"):
        assert (etl_cfg.processed_dir / f"{name}.csv").exists()

    report = json.loads((etl_cfg.interim_dir / "data_quality_report.json")
                        .read_text(encoding="utf-8"))
    # 报告字段与开发文档第 14 节一致
    for key in ("total_rows", "duplicate_rows", "missing_rows", "invalid_rows", "final_rows"):
        assert key in report["summary"]

    beh = pd.read_csv(etl_cfg.processed_dir / "user_behaviors.csv", encoding="utf-8-sig")
    assert len(beh) == report["tables"]["user_behaviors"]["final_rows"]
    assert report["tables"]["user_behaviors"]["source_rows"] == len(beh)  # 生成数据本就干净
    assert beh["behavior_id"].is_unique
    # 冗余列已被重建且自洽
    t = pd.to_datetime(beh["event_time"])
    assert (beh["event_hour"] == t.dt.hour).all()
    assert (beh["event_date"] == t.dt.strftime("%Y-%m-%d")).all()
    # 逻辑外键在清洗后仍成立
    users = set(pd.read_csv(etl_cfg.processed_dir / "users.csv")["user_id"])
    items = set(pd.read_csv(etl_cfg.processed_dir / "items.csv")["item_id"])
    assert beh["user_id"].isin(users).all()
    assert beh["item_id"].isin(items).all()


def test_etl_end_to_end_detects_dirty_data(tmp_path):
    """向生成的原始数据注入脏行，验证 end-to-end 质检报告能识别。"""
    raw = tmp_path / "raw"
    cfg = load_config(output_dir=str(raw), **TEST_GEN)
    run_generation(cfg, log=False)

    # 注入脏行为：重复 behavior_id / 缺 user_id / 非法类型渠道 / 未知商品 / 注册前行为
    beh = pd.read_csv(raw / "user_behaviors.csv", encoding="utf-8-sig")
    first_uid = beh["user_id"].iloc[0]
    first_item = beh["item_id"].iloc[0]
    dirty = pd.DataFrame({
        "behavior_id": [beh["behavior_id"].iloc[0], "BCUSTOM1", "BCUSTOM2", "BCUSTOM3",
                        "BCUSTOM4", "BCUSTOM5", "BCUSTOM6"],
        "user_id": [first_uid, None, "U_NOEXIST", first_uid, first_uid, first_uid, first_uid],
        "item_id": ["I_NOEXIST", first_item, "I_NOEXIST", first_item, "I_NOEXIST", first_item, first_item],
        "behavior_type": ["pv", "pv", "pv", "evil", "pv", "pv", "pv"],
        "event_time": ["2020-01-01 10:00:00", "2026-08-20 10:00:00", "2026-08-20 10:00:00",
                       "2026-08-20 10:00:00", "2026-08-20 10:00:00", "2026-08-20 10:00:00",
                       "2020-01-01 10:00:00"],
        "event_date": ["2020-01-01", "2026-08-20", "2026-08-20", "2026-08-20",
                       "2026-08-20", "2026-08-20", "2020-01-01"],
        "event_hour": [10] * 7,
        "device_type": ["mobile"] * 7,
        "channel": ["organic", "organic", "organic", "organic", "organic", "blackhole", "organic"],
    })
    beh = pd.concat([beh, dirty], ignore_index=True)
    beh.to_csv(raw / "user_behaviors.csv", index=False, encoding="utf-8-sig")

    n_dirty = 7
    out_cfg = load_etl_config(
        raw_dir=str(raw),
        processed_dir=str(tmp_path / "processed"),
        interim_dir=str(tmp_path / "interim"),
        mysql=False,
    )
    run_etl(out_cfg, log=False)
    report = json.loads((out_cfg.interim_dir / "data_quality_report.json")
                        .read_text(encoding="utf-8"))
    summary = report["summary"]
    b_checks = report["tables"]["user_behaviors"]["checks"]
    assert summary["duplicate_rows"] >= 1           # 重复 behavior_id
    assert b_checks["completeness_missing"] >= 1    # user_id 为空
    assert b_checks["legality_invalid"] >= 2        # 非法类型 + 非法渠道
    assert b_checks["consistency_fk"] >= 2          # item/user 不存在
    assert b_checks["time_rule"] >= 1               # 早于用户注册时间
    assert summary["final_rows"] < summary["total_rows"]
    # 清洗后脏行全部被移除（注入 7 行全被丢弃）
    kept_beh = pd.read_csv(out_cfg.processed_dir / "user_behaviors.csv", encoding="utf-8-sig")
    assert len(kept_beh) <= len(beh) - n_dirty


def test_etl_repeatable_no_duplicates(raw_dir, tmp_path):
    """重复执行（skip-mysql）产物字节一致，不产生重复行为/订单。"""
    cfg1 = load_etl_config(raw_dir=str(raw_dir), processed_dir=str(tmp_path / "p1"),
                           interim_dir=str(tmp_path / "i1"), mysql=False)
    cfg2 = load_etl_config(raw_dir=str(raw_dir), processed_dir=str(tmp_path / "p2"),
                           interim_dir=str(tmp_path / "i2"), mysql=False)
    run_etl(cfg1, log=False)
    run_etl(cfg2, log=False)
    for name in ("categories", "users", "items", "user_behaviors", "orders", "order_items"):
        f1 = (tmp_path / "p1" / f"{name}.csv").read_bytes()
        f2 = (tmp_path / "p2" / f"{name}.csv").read_bytes()
        assert f1 == f2, f"{name} 重复执行结果不一致"


# =====================================================================
# 四、MySQL 入库（集成测试，DB 可用时执行）
# =====================================================================
@pytest.fixture(scope="module")
def test_db():
    if not MYSQL_OK:
        pytest.skip("MySQL 不可用")
    import pymysql

    base = load_etl_config()
    db = "ecommerce_recommendation_etltest"

    def _connect(database=None):
        return pymysql.connect(host=base.mysql_host, port=base.mysql_port,
                               user=base.mysql_user, password=base.mysql_password,
                               database=database, charset="utf8mb4", autocommit=True)

    script = (Path(__file__).resolve().parents[1] / "sql" / "schema.sql").read_text(encoding="utf-8")
    statements = []
    buf = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buf).strip())
            buf = []

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{db}`")
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` DEFAULT CHARACTER SET utf8mb4"
                        f" DEFAULT COLLATE utf8mb4_unicode_ci")
        conn.close()
        conn = _connect(db)
        with conn.cursor() as cur:
            for stmt in statements:
                if stmt.upper().startswith(("CREATE DATABASE", "USE")):
                    continue
                cur.execute(stmt)
    finally:
        conn.close()

    cfg = dataclasses.replace(load_etl_config(), mysql_database=db)
    yield cfg

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{db}`")
    finally:
        conn.close()


def _mysql_counts(user, password, host, port, db) -> dict[str, int]:
    import pymysql

    conn = pymysql.connect(host=host, port=port, user=user, password=password, database=db)
    try:
        out = {}
        with conn.cursor() as cur:
            for t in ("categories", "users", "items", "user_behaviors", "orders", "order_items"):
                cur.execute(f"SELECT COUNT(*) FROM `{t}`")
                out[t] = int(cur.fetchone()[0])
        return out
    finally:
        conn.close()


@require_mysql
def test_mysql_load_idempotent(raw_dir, test_db):
    """MySQL 重复加载：行数不变、无重复行为/订单、FK 与冗余列在库内成立。"""
    import pymysql

    runner = dataclasses.replace(
        test_db,
        raw_dir=Path(raw_dir),
        processed_dir=Path(tempfile.mkdtemp()),
        interim_dir=Path(tempfile.mkdtemp()),
    )
    run_etl(runner, log=False)
    c1 = _mysql_counts(test_db.mysql_user, test_db.mysql_password,
                       test_db.mysql_host, test_db.mysql_port, test_db.mysql_database)
    run_etl(runner, log=False)  # 重复执行
    c2 = _mysql_counts(test_db.mysql_user, test_db.mysql_password,
                       test_db.mysql_host, test_db.mysql_port, test_db.mysql_database)
    assert c1 == c2
    assert c1["user_behaviors"] > 0 and c1["orders"] > 0

    conn = pymysql.connect(host=test_db.mysql_host, port=test_db.mysql_port,
                           user=test_db.mysql_user, password=test_db.mysql_password,
                           database=test_db.mysql_database)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM (SELECT behavior_id FROM user_behaviors"
                        " GROUP BY behavior_id HAVING COUNT(*) > 1) x")
            assert int(cur.fetchone()[0]) == 0
            cur.execute("SELECT COUNT(*) FROM (SELECT order_id FROM orders"
                        " GROUP BY order_id HAVING COUNT(*) > 1) x")
            assert int(cur.fetchone()[0]) == 0
            # 逻辑外键在库内成立
            cur.execute("SELECT COUNT(*) FROM user_behaviors b LEFT JOIN users u"
                        " ON b.user_id = u.user_id WHERE u.user_id IS NULL")
            assert int(cur.fetchone()[0]) == 0
            cur.execute("SELECT COUNT(*) FROM order_items oi LEFT JOIN orders o"
                        " ON oi.order_id = o.order_id WHERE o.order_id IS NULL")
            assert int(cur.fetchone()[0]) == 0
            # 冗余列与 event_time 一致
            cur.execute("SELECT COUNT(*) FROM user_behaviors WHERE"
                        " DATE(event_time) <> event_date OR HOUR(event_time) <> event_hour")
            assert int(cur.fetchone()[0]) == 0
    finally:
        conn.close()