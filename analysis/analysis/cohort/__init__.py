"""Cohort 留存分析（Phase 6）。

对应开发文档第 20 节：
- ``cohort_analysis`` 计算按 cohort 的留存矩阵（cohort_date × day_0..day_N），
  供前端热力图展示。
"""

from .cohort import RETENTION_OFFSETS, cohort_analysis

__all__ = ["cohort_analysis", "RETENTION_OFFSETS"]
