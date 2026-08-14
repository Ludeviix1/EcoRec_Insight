"""基础分析模块（Phase 5 + Phase 6）。

对应开发文档第 49.3 / 49.4 节：
- Phase 5：用户规模 / DAU·WAU·MAU / 行为分析 / 活跃时间 / GMV / 商品·分类·品牌排行 / 漏斗；
- Phase 6：留存 / Cohort / RFM。

模块划分：
- ``base``   公共工具（安全除法、数据加载、JSON 落盘、常量）；
- ``config`` 分析配置（processed 目录 / 输出目录 / 版本）；
- ``user``   用户规模 / DAU·WAU·MAU / 行为分析 / 活跃时间；
- ``gmv``    GMV / 订单 / 客单价 / ARPU；
- ``item``   商品排行 / 分类排行 / 品牌排行；
- ``funnel`` 转化漏斗；
- ``retention`` / ``cohort`` 留存与 Cohort 分析；
- ``rfm``    RFM 用户价值分析；
- ``run``    全量分析入口（CLI）。

所有指标函数均为纯函数：输入 ``pd.DataFrame``，输出可直接
``json.dumps`` 的结构化 dict，供后续 FastAPI 直接复用。
"""

from .base import BEHAVIOR_TYPES, CHANNELS, DEVICE_TYPES, ORDER_STATUSES, safe_div

__all__ = ["BEHAVIOR_TYPES", "CHANNELS", "DEVICE_TYPES", "ORDER_STATUSES", "safe_div"]
