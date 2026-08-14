"""转化漏斗分析（Phase 5，开发文档第 19 节）。

标准漏斗：PV → Click → Collect → Cart → Buy。
输出 stage / count / step_conversion_rate / overall_conversion_rate。
"""

from .funnel import conversion_funnel

__all__ = ["conversion_funnel"]
