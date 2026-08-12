"""数据质量模块（Phase 4）。

对外接口：``QualityChecker`` / ``QualityContext`` / ``build_context``。
输出 ``data_quality_report.json``（开发文档第 14 节）。
"""

from .checks import QualityChecker, QualityContext, build_context

__all__ = ["QualityChecker", "QualityContext", "build_context"]