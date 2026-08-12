"""数据清洗（Phase 4）。

职责：对 Phase 3 原始 CSV 分片清洗，输出"可入库"的干净行 + 逐类问题计数。
清洗规则（对应开发文档第 14 节）：
- 完整性：required_fields 非空（与 MySQL NOT NULL 列一致）；
- 合法性：枚举取值 / 数值边界 / 时间可解析；event_date、event_hour 冗余列以
  event_time 重建（保证与源一致性约束，开发文档第 9 节）；
- 唯一性：按业务主键（或整行）去重；
- 一致性（逻辑外键）与时间（不早于注册、不晚于截止日）由 quality 模块完成，
  因为需要跨表参照，不在本模块重复实现。

实现要点：所有检查均向量化（Pandas 布尔掩码），复杂度 O(n)；返回 (kept, stats)
保持纯粹性，方便单元测试。

输入：pd.DataFrame（源列与 TableSpec.columns 一致）
输出：(清洗后 DataFrame, stats dict)，stats 的 dropped 为去重后的最终丢弃数。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..etl.specs import TableSpec


def clean_chunk(df: pd.DataFrame, spec: TableSpec) -> tuple[pd.DataFrame, dict]:
    """清洗一个分片，返回 (kept 行, 统计 dict)。

    统计字段：rows_in / missing / illegal / duplicates / dropped / kept。
    dropped 为三种问题合并后的真实丢弃行数（同批数据不清洗二次）。
    """
    stats = {"rows_in": int(len(df))}
    work = df.copy()

    # 1) 字符串去空格 + 空值统一为 None
    text_cols = [c for c in work.columns if _is_text_dtype(work[c])]
    for col in text_cols:
        work[col] = _coerce_str(work[col])

    # 2) 完整性：必需列非空（基于原始输入值判断，时间解析失败不计为缺失）
    missing_mask = pd.Series(False, index=work.index)
    for col in spec.required_fields:
        if col not in work.columns:
            continue
        missing_mask |= _is_missing(work[col])
    stats["missing"] = int(missing_mask.sum())

    # 3) 时间解析（解析失败且原值非空 -> illegal）
    illegal_dt_mask = pd.Series(False, index=work.index)
    for col in spec.datetime_fields:
        if col not in work.columns:
            continue
        raw_valid = work[col].notna()
        parsed = pd.to_datetime(work[col], errors="coerce")
        illegal_dt = raw_valid & parsed.isna()
        illegal_dt_mask |= illegal_dt
        _accum(stats, "illegal_dt", illegal_dt.sum())
        work[col] = parsed

    # 4) 冗余列重建（event_date / event_hour 与 event_time 保持一致）
    if spec.recompute_date_hour and "event_time" in work.columns:
        et = work["event_time"]
        valid = et.notna()
        work.loc[valid, "event_date"] = et[valid].dt.strftime("%Y-%m-%d")
        work.loc[valid, "event_hour"] = et[valid].dt.hour.astype("Int64")

    # 5) 合法性：时间解析失败 + 枚举取值 + 数值边界
    illegal_mask = illegal_dt_mask.copy()
    # 5.1 枚举（统一转为字符串比较，兼容 int 列如 items.status）
    for col, allowed in spec.allowed_values.items():
        if col not in work.columns:
            continue
        cur = _coerce_str(work[col])
        illegal_mask |= cur.notna() & ~cur.isin(allowed)
    # 5.2 数值：非数值文本 / 越界
    for col, lo in {**spec.min_values, **spec.gt_values}.items():
        if col not in work.columns:
            continue
        num = _as_number(work[col])
        bad_parse = work[col].notna() & num.isna()
        if col in spec.min_values:
            bad_parse |= num.lt(spec.min_values[col]) & work[col].notna()
        if col in spec.gt_values:
            bad_parse |= num.le(spec.gt_values[col]) & work[col].notna()
        illegal_mask |= bad_parse
    for col, hi in spec.max_values.items():
        if col not in work.columns:
            continue
        num = _as_number(work[col])
        illegal_mask |= num.gt(hi) & work[col].notna()
    # 5.3 无界数值列（如 event_hour 重建失效时为 None，不影响此处）
    stats["illegal"] = int(illegal_mask.sum())

    # 6) 类型收敛：整数列转 Int64（保留 None -> 后续按 nullable 处理）
    for col, _ in {**spec.min_values, **spec.gt_values, **spec.max_values}.items():
        if col in work.columns:
            work[col] = _as_number(work[col])

    # 7) 唯一性：业务主键或整行去重
    dup_mask = pd.Series(False, index=work.index)
    if spec.unique_key and spec.unique_key in work.columns:
        dup_mask |= work[spec.unique_key].duplicated(keep="first")
    else:
        dup_mask |= work.duplicated(keep="first")
    stats["duplicates"] = int(dup_mask.sum())

    # 8) 合并丢弃（三种问题取并集），保留干净行
    drop_mask = missing_mask | illegal_mask | dup_mask
    kept = work[~drop_mask].reset_index(drop=True).copy()
    stats["dropped"] = int(drop_mask.sum())
    stats["kept"] = int(len(kept))
    return kept, stats


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------
def _is_text_dtype(s: pd.Series) -> bool:
    return s.dtype == object or str(s.dtype) in ("string", "str")


def _coerce_str(s: pd.Series) -> pd.Series:
    """对象列统一转字符串并去首尾空白；空值保持 None。"""
    s = s.astype(object)
    na = s.isna()
    out = s.astype(str).str.strip()
    out[na] = None
    return out


def _is_missing(s: pd.Series) -> pd.Series:
    """缺失 = None / 空串（数值列 NaN 亦为缺失）。"""
    if _is_text_dtype(s) or str(s.dtype) == "string":
        return s.isna() | (s.astype(object) == "")
    return s.isna()


def _as_number(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype("Float64")
    return pd.to_numeric(s.astype(object).where(s.notna(), None), errors="coerce").astype("Float64")


def _accum(stats: dict, key: str, value) -> None:
    stats[key] = int(stats.get(key, 0)) + int(value)


def sum_stats(acc: dict, stats: dict) -> dict:
    """累加多分片统计。"""
    for key, val in stats.items():
        acc[key] = int(acc.get(key, 0)) + int(val)
    return acc


def validate_header(header: pd.Index, spec: TableSpec) -> list[str]:
    """schema 校验：返回缺失列清单（开发文档 Phase 4：Schema Validation）。"""
    return [c for c in spec.columns if c not in header]