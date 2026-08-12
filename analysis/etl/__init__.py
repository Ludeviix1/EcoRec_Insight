"""数据质量 + ETL 模块（Phase 4）。

- ``specs``    六张核心表 ETL 规格（清洗/质检/入库共用）；
- ``cleaning`` Raw CSV 逐批清洗（完整性 / 合法性 / 唯一性 / 冗余列重建）；
- ``quality``  一致性（逻辑外键）与时间检查 + data_quality_report.json；
- ``loader``   MySQL 批量写入，refresh 幂等；
- ``pipeline`` Raw -> Schema -> Cleaning -> Quality -> Transformation -> Processed -> MySQL；
- ``run``      CLI 入口。

注意：本包 __init__ 刻意保持轻量，避免与 ``cleaning`` / ``quality`` 形成环状导入；
流水线入口请直接 ``from analysis.etl.pipeline import run_etl``。
"""

from .config import EtlConfig, load_etl_config

ETL_ORDER_TABLES = ("categories", "users", "items", "user_behaviors", "orders", "order_items")

__all__ = ["EtlConfig", "load_etl_config", "ETL_ORDER_TABLES"]