"""Dashboard 服务：汇总 /api/dashboard/* 各端点需要的分析产物。

分析 JSON（data/analysis/*.json）顶层即为指标字段，直接读取。
"""

from __future__ import annotations

from ..repositories import analysis_repo


def overview() -> dict:
    """总体 KPI：用户数、活跃、购买、订单、GMV、客单价、ARPU、最新 DAU/MAU。"""
    us = analysis_repo.get_item("user-scale")
    g = analysis_repo.get_item("gmv")
    d = analysis_repo.get_item("dau-wau-mau")

    def _latest(key: str) -> dict | None:
        rows = d.get(key) or []
        return rows[-1] if rows else None

    return {
        "total_users": us.get("total_users"),
        "new_users": us.get("new_users"),
        "active_users": us.get("active_users"),
        "buying_users": us.get("buying_users"),
        "pay_rate": us.get("pay_rate"),
        "gmv_total": g.get("gmv_total"),
        "order_count": g.get("order_count"),
        "aov": g.get("aov"),
        "arpu": g.get("arpu"),
        "dau_latest": d.get("latest_dau") or _latest("dau"),
        "wau_latest": d.get("latest_wau") or _latest("wau"),
        "mau_latest": d.get("latest_mau") or _latest("mau"),
    }


def user_trend() -> dict:
    """用户趋势：DAU / WAU / MAU、注册趋势、性别与城市分布。"""
    us = analysis_repo.get_item("user-scale")
    d = analysis_repo.get_item("dau-wau-mau")
    return {
        "dau": d.get("dau"),
        "wau": d.get("wau"),
        "mau": d.get("mau"),
        "register_trend": us.get("register_trend"),
        "gender_distribution": us.get("gender_distribution"),
        "city_distribution": us.get("city_distribution"),
    }


def gmv_trend() -> dict:
    """GMV 趋势：日 / 周 / 月 维度的 GMV、订单数、购买用户、客单价、ARPU。"""
    g = analysis_repo.get_item("gmv")
    return {
        "daily_trend": g.get("daily_trend"),
        "weekly_trend": g.get("weekly_trend"),
        "monthly_trend": g.get("monthly_trend"),
        "status_distribution": g.get("status_distribution"),
    }


def behavior_trend() -> dict:
    """行为趋势：5 类行为计数 / 转化率、按小时与工作日活跃分布。"""
    b = analysis_repo.get_item("behavior")
    at = analysis_repo.get_item("active-time")
    return {
        "total": b.get("total"),
        "counts": b.get("counts"),
        "rates": b.get("rates"),
        "daily_trend": b.get("daily_trend"),
        "by_hour": at.get("by_hour"),
        "by_weekday": at.get("by_weekday"),
        "by_device_hour": at.get("by_device_hour"),
    }


def funnel() -> dict:
    """转化漏斗：PV → Click → Collect → Cart → Buy。"""
    f = analysis_repo.get_item("funnel")
    return {
        "definition": f.get("definition"),
        "stages": f.get("stages"),
        "steps": f.get("steps"),
    }


def retention() -> dict:
    """留存：整体留存率 + Cohort 留存矩阵（热力图数据）。"""
    r = analysis_repo.get_item("retention")
    c = analysis_repo.get_item("cohort")
    return {
        "definition": r.get("definition"),
        "offsets": r.get("offsets"),
        "overall": r.get("overall"),
        "cohort_base": c.get("cohort_base"),
        "cohort_offsets": c.get("offsets"),
        "cohorts": c.get("cohorts"),
    }