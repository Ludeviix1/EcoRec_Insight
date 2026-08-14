"""留存分析（Phase 6）。

对应开发文档第 20.1 节：
- ``retention_analysis`` 计算次日/3日/7日/14日/30日留存（按 cohort）。
"""

from .retention import RETENTION_LABELS, retention_analysis

__all__ = ["retention_analysis", "RETENTION_LABELS"]
