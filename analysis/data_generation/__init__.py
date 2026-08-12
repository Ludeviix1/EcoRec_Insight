"""数据生成模块（Phase 3）。

依据 `开发文档2.1.md` 第 6~13 节生成具有业务规律的模拟数据：
- 用户偏好（每用户 1~3 个偏好分类）
- 商品热度（热门商品更高曝光）
- 行为链（PV -> Click -> Collect/Cart -> Buy 概率关联）
- 时间规律（晚间 + 周末活跃度更高）
- 用户价值分层（高 / 中 / 低）
- 渠道差异（不同渠道点击率 / 转化率 / 用户质量不同）

入口：``python scripts/generate_data.py``，输出 CSV 到 ``data/raw/``。
"""

from .config import DataGenConfig, load_config
from .generate import run_generation

__all__ = ["DataGenConfig", "load_config", "run_generation"]
