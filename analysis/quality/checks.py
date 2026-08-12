"""数据质量检查（Phase 4）。

对应开发文档第 14 节五类检查：
- 完整性（completeness）：字段非空 -> 由 cleaning 完成；
- 唯一性（uniqueness）：business key / 整行去重 -> cleaning + 全局去重；
- 合法性（legality）：枚举取值 / 数值边界 / 时间可解析 -> 由 cleaning 完成；
- 一致性（consistency）：逻辑外键引用存在（行为-用户/商品、订单-用户、
  明细-订单/商品、分类父子）；
- 时间（time）：事件/订单不早于用户注册时间、不晚于数据截止日。

本模块负责需要跨表上下文的 一致性 与 时间 检查，以及汇总报告结构；
清洗内置的 完整性/合法性/唯一性 统计由 pipeline 聚合并写入报告。

输出 data_quality_report.json（开发文档第 14 节）：
    {"total_rows","duplicate_rows","missing_rows","invalid_rows","final_rows"}
    + 每表明细。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..etl.specs import TableSpec


@dataclass(frozen=True)
class QualityContext:
    """质检所需的跨表参照数据。"""

    user_ids: frozenset = frozenset()
    item_ids: frozenset = frozenset()
    category_ids: frozenset = frozenset()
    order_ids: frozenset = frozenset()
    register_time: dict = field(default_factory=dict)   # user_id -> Timestamp
    data_end: pd.Timestamp | None = None                # 数据截止时间（含）


class QualityChecker:
    """封装一致性 / 时间检查，返回 (bad_mask, count) 向量化结果。"""

    def __init__(self, ctx: QualityContext):
        self.ctx = ctx

    # ---- 一致性（逻辑外键，开发文档第 14 节）----
    def consistency(self, df: pd.DataFrame, spec: TableSpec) -> tuple[pd.Series, dict]:
        ref_sets = {
            "categories": self.ctx.category_ids,
            "users": self.ctx.user_ids,
            "items": self.ctx.item_ids,
            "orders": self.ctx.order_ids,
        }
        mask = pd.Series(False, index=df.index)
        per_field: dict[str, int] = {}
        for field, (ref_table, _) in spec.fk_refs.items():
            if field not in df.columns:
                continue
            bad = df[field].notna() & ~df[field].isin(ref_sets[ref_table])
            mask |= bad
            per_field[field] = int(bad.sum())
        return mask, per_field

    # ---- 时间（开发文档第 14 节）----
    def time(self, df: pd.DataFrame, spec: TableSpec) -> tuple[pd.Series, dict]:
        mask = pd.Series(False, index=df.index)
        per_col: dict[str, int] = {}
        for col, ref_table in (("event_time", "user_id"), ("order_time", "user_id")):
            if col not in df.columns:
                continue
            ts = pd.to_datetime(df[col], errors="coerce")
            valid = ts.notna()
            if ref_table in df.columns:
                reg = df[ref_table].map(self.ctx.register_time)
                reg_ok = reg.notna()
                before = valid & reg_ok & (ts < reg)
                mask |= before
                per_col[f"{col}<register"] = int(before.sum())
            if self.ctx.data_end is not None:
                after = valid & (ts > self.ctx.data_end)
                mask |= after
                per_col[f"{col}>data_end"] = int(after.sum())
        return mask, per_col

    # ---- 跨分片唯一性（全局 business key 去重）----
    @staticmethod
    def global_duplicates(df: pd.DataFrame, spec: TableSpec, seen: set) -> tuple[pd.Series, int]:
        keys = df[spec.unique_key] if spec.unique_key else df.apply(tuple, axis=1)
        dup = keys.isin(seen)
        seen.update(keys[~dup].tolist())
        return dup, int(dup.sum())


def build_context(
    *,
    user_ids,
    item_ids,
    category_ids,
    order_ids,
    register_time,
    data_end: pd.Timestamp | None,
) -> QualityContext:
    """从已清洗的维度表构建质检上下文。"""
    return QualityContext(
        user_ids=frozenset(user_ids),
        item_ids=frozenset(item_ids),
        category_ids=frozenset(category_ids),
        order_ids=frozenset(order_ids),
        register_time=register_time,
        data_end=data_end,
    )