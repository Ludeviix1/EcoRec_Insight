"""ETL 流水线（Phase 4）。

流程（开发文档第 49.2 节 / 第 15 节）：
    Raw CSV -> Schema Validation -> Cleaning -> Quality Report
           -> Transformation -> Processed CSV -> MySQL

特性：
- 大文件批量读取（read_csv chunksize）与批量写入（csv 分片追加 + executemany 批量插入）；
- 可重复执行：refresh 模式先清空 MySQL 核心表再 INSERT IGNORE，重复运行不产生重复行；
- 生成 dataset_version / etl_version / generator_version / 运行记录（开发文档第 E 节）；
- 输出 data/interim/data_quality_report.json 与 data/interim/etl_meta.json；
- 输出 data/processed/ 六张清洗后 CSV（供 Phase 5 之后全量分析消费）。

输入：data/raw/ 下 Phase 3 CSV + data_meta.json
输出：data/processed/ *_clean 数据、data/interim/ 质检报告与 ETL 运行记录、（可选）MySQL
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..cleaning import clean_chunk, sum_stats, validate_header
from ..quality import QualityChecker, build_context
from .config import EtlConfig
from .loader import MySQLLoader
from .specs import ETL_ORDER, TABLE_SPECS, TableSpec

logger = logging.getLogger("etl.pipeline")


def run_etl(cfg: EtlConfig, *, log: bool = True) -> dict:
    """执行完整 ETL，返回 etl_meta dict。"""
    if log:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    t0 = time.perf_counter()
    cfg.raw_dir.mkdir(parents=True, exist_ok=True)
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)
    cfg.interim_dir.mkdir(parents=True, exist_ok=True)

    # ---- 读取生成期 meta（开发文档第 E 节：generator_version / 时间范围）----
    meta_file = cfg.raw_dir / "data_meta.json"
    gen_meta: dict = {}
    if meta_file.exists():
        gen_meta = json.loads(meta_file.read_text(encoding="utf-8"))
    gen_version = gen_meta.get("schema_version")
    meta_end = gen_meta.get("data_end_date")
    window_days = int(gen_meta.get("behavior_window_days", 90))
    # 数据截止时间（含）
    scope = {"data_time": None, "min_event": None, "max_event": None}
    if meta_end:
        scope["data_time"] = pd.Timestamp(f"{meta_end} 23:59:59")

    # ---- MySQL：refresh 模式先清空核心表（保证幂等）----
    loader = MySQLLoader(cfg) if cfg.mysql else None
    if loader and cfg.mode == "refresh":
        loader.truncate()

    # ---- 六表顺序处理（维度 -> 事实，逻辑外键始终成立）----
    reports: dict[str, dict] = {}
    processed_counts: dict[str, int] = {}
    order_amount_sum: dict[str, float] = {}
    for table in ETL_ORDER:
        spec = TABLE_SPECS[table]
        report, kept, t_lo, t_hi = _process_table(
            cfg, spec, loader_ref=loader, order_amount_sum=order_amount_sum,
        )
        reports[table] = report
        processed_counts[table] = int(kept)
        scope["min_event"] = _min(scope["min_event"], t_lo)
        scope["max_event"] = _max(scope["max_event"], t_hi)

    # ---- Transformation：订单金额 = 明细金额之和（开发文档第 11 节一致性）----
    if order_amount_sum:
        _transform_orders(cfg, loader, order_amount_sum)

    # ---- 质量报告（开发文档第 14 节）----
    report = _build_report(reports, cfg)
    cfg.quality_report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- ETL 运行记录 ----
    mysql_counts = loader.table_counts() if loader else None
    data_start = scope["min_event"] or (scope["data_time"] - timedelta(days=window_days))
    data_end = scope["max_event"] or scope["data_time"]

    meta = {
        "dataset_version": cfg.dataset_version,
        "etl_version": cfg.etl_version,
        "generator_version": gen_version,
        "data_start_time": str(data_start),
        "data_end_time": str(data_end),
        "anchor_end_date": str(meta_end),
        "mode": cfg.mode,
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "chunk_size": cfg.chunk_size,
        "raw_dir": str(cfg.raw_dir),
        "processed_dir": str(cfg.processed_dir),
        "interim_dir": str(cfg.interim_dir),
        "quality_report": str(cfg.quality_report_path),
        "summary": report["summary"],
        "mysql_counts": mysql_counts,
    }
    cfg.etl_meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if loader:
        loader.close()

    logger.info("ETL done in %ss | processed=%s | mysql=%s",
                meta["elapsed_seconds"], processed_counts, mysql_counts)
    return meta


# ----------------------------------------------------------------------
# 单表处理
# ----------------------------------------------------------------------
def _process_table(
    cfg: EtlConfig,
    spec: TableSpec,
    *,
    loader_ref: MySQLLoader | None,
    order_amount_sum: dict[str, float],
) -> tuple[dict, int, object, object]:
    """批式处理单张表：清洗 -> 质检 -> 写 processed CSV -> （可选）批量入库。

    返回 (报告 dict, 最终保留行数, 最小事件时间, 最大事件时间)。
    """
    raw_path = cfg.raw_dir / spec.source_file
    proc_path = cfg.processed_dir / spec.processed_file
    if not raw_path.exists():
        raise FileNotFoundError(f"原始数据缺失: {raw_path}")

    # 参照上下文（users/items/categories/orders 已先于本表处理，orders 已处理）
    refs = _load_reference_frame(cfg, current_table=spec.name)
    ctx = build_context(
        user_ids=refs["users"],
        item_ids=refs["items"],
        category_ids=refs["categories"],
        order_ids=refs["orders"],
        register_time=refs["register"],
        data_end=_data_end(cfg),
    )
    checker = QualityChecker(ctx)

    acc = {"rows": 0, "missing": 0, "illegal": 0, "duplicates": 0, "fk": 0, "time": 0, "kept": 0}
    fk_detail: dict[str, int] = {}
    time_detail: dict[str, int] = {}
    seen: set = set()
    min_ts = max_ts = None

    header_written = False
    with proc_path.open("wb") as fh:
        fh.write(b"\xef\xbb\xbf")  # UTF-8 BOM，与 raw CSV 保持一致
        for chunk_no, chunk in enumerate(pd.read_csv(raw_path, chunksize=cfg.chunk_size, encoding="utf-8-sig")):
            if chunk_no == 0:
                missing_cols = validate_header(chunk.columns, spec)
                if missing_cols:
                    raise ValueError(f"schema 校验失败 {spec.name}: 缺失列 {missing_cols}")

            acc["rows"] += len(chunk)
            cleaned, stats = clean_chunk(chunk, spec)
            acc["missing"] += stats["missing"]
            acc["illegal"] += stats["illegal"]

            # 全局唯一性（跨分片）
            dup_mask, n_dup = QualityChecker.global_duplicates(cleaned, spec, seen)
            cleaned = cleaned[~dup_mask]
            acc["duplicates"] += stats["duplicates"] + n_dup

            # 一致性（逻辑外键）
            fk_mask, fkp = checker.consistency(cleaned, spec)
            cleaned = cleaned[~fk_mask]
            acc["fk"] += int(fk_mask.sum())
            _add_counts(fk_detail, fkp)

            # 时间
            t_mask, tp = checker.time(cleaned, spec)
            cleaned = cleaned[~t_mask]
            acc["time"] += int(t_mask.sum())
            _add_counts(time_detail, tp)

            acc["kept"] += len(cleaned)

            # 行为时间范围（供 dataset 时间窗口记录）
            if spec.name == "user_behaviors" and len(cleaned):
                et = pd.to_datetime(cleaned["event_time"])
                lo, hi = et.min(), et.max()
                min_ts = lo if min_ts is None or lo < min_ts else min_ts
                max_ts = hi if max_ts is None or hi > max_ts else max_ts

            # 订单明细金额累加（Transformation 用）
            if spec.name == "order_items" and len(cleaned):
                for oid, amt in zip(cleaned["order_id"], cleaned["amount"]):
                    order_amount_sum[oid] = order_amount_sum.get(oid, 0.0) + float(amt)

            if not len(cleaned):
                continue
            cleaned.to_csv(fh, index=False, header=not header_written, encoding="utf-8")
            header_written = True

            rows = _to_mysql_rows(cleaned, spec)
            if loader_ref:
                loader_ref.bulk_insert(spec, rows, cfg.chunk_size)

    report = {
        "table": spec.name,
        "mysql_table": spec.mysql_table,
        "source_rows": acc["rows"],
        "checks": {
            "completeness_missing": acc["missing"],
            "uniqueness_duplicates": acc["duplicates"],
            "legality_invalid": acc["illegal"],
            "consistency_fk": acc["fk"],
            "time_rule": acc["time"],
        },
        "fk_detail": fk_detail,
        "time_detail": time_detail,
        "dropped_rows": acc["rows"] - acc["kept"],
        "final_rows": acc["kept"],
    }
    return report, acc["kept"], min_ts, max_ts


# ----------------------------------------------------------------------
# Transformation：订单金额与明细对账
# ----------------------------------------------------------------------
def _transform_orders(cfg: EtlConfig, loader: MySQLLoader | None, amount_sum: dict[str, float]) -> None:
    """用 order_items 的 amount 之和重算 orders.total_amount（开发文档第 11 节）。"""
    proc_orders = cfg.processed_dir / "orders.csv"
    if not proc_orders.exists():
        return
    orders = pd.read_csv(proc_orders, encoding="utf-8-sig")
    computed = orders["order_id"].map(amount_sum)
    mismatch = computed.notna() & (orders["total_amount"].round(2) != computed.round(2))
    if int(mismatch.sum()) == 0:
        logger.info("orders.total_amount 与 order_items 明细一致，无需修正")
        return
    logger.warning("orders.total_amount 差异 %d 行，按明细重算", int(mismatch.sum()))
    ids = orders.loc[mismatch, "order_id"].tolist()
    pairs = [(round(float(amount_sum[oid]), 2), oid) for oid in ids]
    if loader:
        loader.update("orders", "total_amount", "order_id", pairs)
    orders.loc[mismatch, "total_amount"] = orders.loc[mismatch, "order_id"].map(amount_sum).round(2)
    orders.to_csv(proc_orders, index=False, encoding="utf-8-sig")


# ----------------------------------------------------------------------
# 辅助
# ----------------------------------------------------------------------
def _load_reference_frame(cfg: EtlConfig, current_table: str | None = None) -> dict:
    """加载已清洗维度表构建参照（users/items/categories/orders）。

    自引用表（如分类的父子引用）在其它参照尚未生成时，以源数据全量键值作为参照，
    保证"父分类引用已存在分类"的检查不误删数据。
    """
    out = {"users": set(), "items": set(), "categories": set(), "orders": set(), "register": {}}
    for name, col, ref in (
        ("users", "user_id", "users"),
        ("items", "item_id", "items"),
        ("categories", "category_id", "categories"),
        ("orders", "order_id", "orders"),
    ):
        p = cfg.processed_dir / f"{name}.csv"
        if not p.exists() or p.stat().st_size <= 3:  # 只有 BOM 无数据 -> 视为空
            continue
        try:
            df_proc = pd.read_csv(p, encoding="utf-8-sig")
        except pd.errors.EmptyDataError:
            continue
        out[ref] = set(df_proc[col].dropna().tolist())

    reg = {}
    p = cfg.processed_dir / "users.csv"
    if p.exists() and p.stat().st_size > 3:
        try:
            dfu = pd.read_csv(p, encoding="utf-8-sig")
        except pd.errors.EmptyDataError:
            dfu = pd.DataFrame()
        if len(dfu):
            reg = {uid: ts for uid, ts in
                   zip(dfu["user_id"], pd.to_datetime(dfu["register_time"], errors="coerce"))}
    out["register"] = reg

    # 自引用补充：分类父子 / 本表即以自身键集为参照
    if current_table and current_table in out:
        spec = TABLE_SPECS[current_table]
        src = cfg.raw_dir / spec.source_file
        if src.exists() and spec.unique_key and spec.unique_key in spec.columns:
            keys = set(pd.read_csv(src, usecols=[spec.unique_key], encoding="utf-8-sig")
                       [spec.unique_key].dropna().tolist())
            out[current_table] |= keys
    return out


def _data_end(cfg: EtlConfig) -> pd.Timestamp | None:
    meta_file = cfg.raw_dir / "data_meta.json"
    end = None
    if meta_file.exists():
        end = json.loads(meta_file.read_text(encoding="utf-8")).get("data_end_date")
    return pd.Timestamp(f"{end} 23:59:59") if end else None


def _build_report(reports: dict[str, dict], cfg: EtlConfig) -> dict:
    summary = {
        "total_rows": sum(r["source_rows"] for r in reports.values()),
        "duplicate_rows": sum(r["checks"]["uniqueness_duplicates"] for r in reports.values()),
        "missing_rows": sum(r["checks"]["completeness_missing"] for r in reports.values()),
        "invalid_rows": sum(r["checks"]["legality_invalid"] for r in reports.values()),
        "final_rows": sum(r["final_rows"] for r in reports.values()),
    }
    return {
        "dataset_version": cfg.dataset_version,
        "etl_version": cfg.etl_version,
        "report_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "tables": reports,
    }


def _to_mysql_rows(df: pd.DataFrame, spec: TableSpec) -> list[tuple]:
    df = df.copy()
    # 整型化：整值浮点列转 Int64，避免 "0.0" 写入 TINYINT/INT 触发 MySQL 严格模式
    for col in spec.mysql_columns:
        s = df[col]
        if str(s.dtype) == "Float64" and not s.isna().any():
            arr = s.astype(float)
            if (arr % 1 == 0).all():
                df[col] = arr.astype("Int64")

    cols = list(spec.mysql_columns)
    rows = []
    for rec in df.to_dict("records"):
        rows.append(tuple(_to_db_value(rec.get(c)) for c in cols))
    return rows


def _to_db_value(v):
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, str):
        return v if v != "" else None
    try:
        if pd.isna(v) or pd.isnull(v):
            return None
    except Exception:
        pass
    if hasattr(v, "item") and not isinstance(v, (pd.Timestamp, datetime)):
        try:
            return v.item()
        except Exception:
            return v
    return v


def _add_counts(target: dict[str, int], src: dict[str, int]) -> None:
    for k, v in src.items():
        target[k] = int(target.get(k, 0)) + int(v)


def _min(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a if a < b else b


def _max(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return a if a > b else b