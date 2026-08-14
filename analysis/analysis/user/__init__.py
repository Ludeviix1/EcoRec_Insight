"""用户基础分析（Phase 5）。

- ``scale``       用户规模（总用户 / 新增 / 活跃 / 购买 / 付费率）；
- ``dau``         DAU / WAU / MAU；
- ``behavior``    行为分析（PV/Click/Collect/Cart/Buy + 转化率）；
- ``active_time`` 活跃时间（hour / weekday / device）。
"""

from .active_time import active_time
from .behavior import behavior_analysis
from .dau import dau_wau_mau
from .scale import user_scale

__all__ = ["user_scale", "dau_wau_mau", "behavior_analysis", "active_time"]
