"""Cohort 留存分析（开发文档第 20 节）。

口径（明确定义）：
- cohort 起点（cohort_base）：
    * ``first_behavior``（默认）：用户首次产生行为（首次活跃）的日期；
    * ``register``：用户注册日期（需要 users 表的 register_time）。
- 留存定义：第 N 日留存 = cohort 中在首次活跃后的第 N 天仍产生行为的用户数 /
  cohort 规模（day_0）。
- 输出 day_0 / day_1 / day_3 / day_7 / day_14 / day_30 及对应留存率，
  供前端热力图展示（cohort_date × day）。
"""

from __future__ import annotations

import pandas as pd

from ..base import safe_div

# 默认留存周期（天）
RETENTION_OFFSETS: tuple[int, ...] = (1, 3, 7, 14, 30)


def cohort_analysis(
    behaviors: pd.DataFrame,
    users: pd.DataFrame | None = None,
    *,
    cohort_base: str = "first_behavior",
    offsets: tuple[int, ...] = RETENTION_OFFSETS,
) -> dict:
    """计算按 cohort 的留存矩阵。

    参数:
        behaviors: user_behaviors，至少含 user_id / event_date
        users: users，至少含 user_id / register_time（仅 cohort_base="register" 时需要）
        cohort_base: "first_behavior"（首次活跃）或 "register"（注册日）
        offsets: 留存周期列表（天）

    返回:
        dict:
        - cohort_base / offsets
        - cohorts: list[{"cohort_date","size", "day_0", "day_<d>", "rate_day_<d>"}]
        - aggregate: 整体留存率 {day_<d>: rate}（按 cohort 规模加权）
    """
    cohort_date = _cohort_dates(behaviors, users, cohort_base)

    # 每个用户在每天是否活跃（去重）
    active = behaviors[["user_id", "event_date"]].copy()
    active["event_date"] = pd.to_datetime(active["event_date"], errors="coerce").dt.normalize()
    active = active.dropna(subset=["event_date"]).drop_duplicates()

    # day_0 = cohort 规模
    sizes = cohort_date.groupby("cohort_date").size()
    all_cohort_dates = sorted(sizes.index)

    rows = []
    for cd in all_cohort_dates:
        size = int(sizes.loc[cd])
        cohort_users = set(cohort_date.loc[cohort_date["cohort_date"] == cd, "user_id"])
        row: dict = {"cohort_date": str(cd.date()), "size": size}
        for d in offsets:
            target = cd + pd.Timedelta(days=d)
            sub = active[
                (active["event_date"] == target) & (active["user_id"].isin(cohort_users))
            ]
            row[f"day_{d}"] = int(sub["user_id"].nunique())
        row["day_0"] = size
        rows.append(row)

    # 整体留存率：按 cohort 规模加权（各 day 求和 / day_0 求和）
    aggregate: dict = {}
    for d in offsets:
        total_day_d = sum(r[f"day_{d}"] for r in rows)
        total_size = sum(r["day_0"] for r in rows)
        aggregate[f"day_{d}"] = safe_div(total_day_d, total_size)
        for r in rows:
            r[f"rate_day_{d}"] = safe_div(r[f"day_{d}"], r["day_0"])

    return {
        "cohort_base": cohort_base,
        "offsets": [0, *list(offsets)],
        "total_cohorts": len(rows),
        "total_users": int(cohort_date["user_id"].nunique()),
        "cohorts": rows,
        "aggregate": aggregate,
    }


def _cohort_dates(
    behaviors: pd.DataFrame,
    users: pd.DataFrame | None,
    cohort_base: str,
) -> pd.DataFrame:
    """返回 user_id → cohort_date 表（首次活跃日或注册日）。"""
    if cohort_base == "register":
        if users is None or "register_time" not in users.columns:
            raise ValueError("cohort_base='register' 需要传入含 register_time 的 users 表")
        out = users[["user_id", "register_time"]].copy()
        out["cohort_date"] = pd.to_datetime(out["register_time"], errors="coerce").dt.normalize()
        return out.dropna(subset=["cohort_date"]).drop_duplicates(subset=["user_id"])

    if cohort_base != "first_behavior":
        raise ValueError(f"不支持的 cohort_base: {cohort_base}")

    df = behaviors[["user_id", "event_date"]].copy()
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["event_date"])
    return (
        df.groupby("user_id")["event_date"]
        .min()
        .rename("cohort_date")
        .reset_index()
    )
