"""数据生成配置（Phase 3）。

设计要点：
- 数据量可配置：支持环境变量（``DATA_USERS`` 等）与 CLI 覆盖，对应开发文档第 12 节。
- 可复现：``RANDOM_STATE = 42`` 固定随机种子；``DATA_END_DATE`` 固定数据截止日，
  避免使用"当前时间"导致每次生成结果漂移（开发文档第 47 节）。
- 与后端 ``backend/app/core/config.py`` 解耦：数据生成只产 CSV，不连数据库
  （入库是 Phase 4 ETL 的职责），因此独立维护一份配置。

输入：环境变量 / CLI 参数
输出：``DataGenConfig`` 不可变配置对象
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# 项目根目录（analysis/data_generation/config.py -> 上溯两级 = 项目根）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"

# 开发文档第 47 节：统一随机种子，保证可复现
RANDOM_STATE = 42

# 固定数据截止日（含）。行为窗口 = [DATA_END_DATE - behavior_window_days, DATA_END_DATE]。
# 用固定日期而非 today()，确保不同时间生成的数据时间范围一致。
DEFAULT_DATA_END_DATE = date(2026, 8, 31)


# ---------------------------------------------------------------------
# 规模预设（开发文档第 12 节）
# ---------------------------------------------------------------------
SCALE_PRESETS: dict[str, dict] = {
    # 低配电脑默认：用户 2,000 / 商品 1,000 / 行为 100,000 / 订单 ~10,000
    "low": {
        "n_users": 2_000,
        "n_items": 1_000,
        "n_behaviors": 100_000,
    },
    # 建议最终规模：用户 10,000 / 商品 5,000 / 行为 500,000 / 订单 ~50,000
    "standard": {
        "n_users": 10_000,
        "n_items": 5_000,
        "n_behaviors": 500_000,
    },
    # 上限规模：用户 10,000 / 商品 5,000 / 行为 2,000,000 / 订单 ~150,000
    "large": {
        "n_users": 10_000,
        "n_items": 5_000,
        "n_behaviors": 2_000_000,
    },
}


@dataclass(frozen=True)
class DataGenConfig:
    """数据生成全部可调参数。

    n_behaviors 为 user_behaviors 表的目标行数（近似，实际由行为链自然展开决定）；
    orders / order_items 由 buy 行为派生，行数随之产生并在 meta 中记录实际值。
    """

    # ---- 数据量 ----
    n_users: int = 2_000
    n_items: int = 1_000
    n_behaviors: int = 100_000

    # ---- 可复现性 ----
    random_state: int = RANDOM_STATE
    data_end_date: date = DEFAULT_DATA_END_DATE
    behavior_window_days: int = 90          # 行为发生窗口长度（天）
    registration_window_days: int = 365     # 注册时间分布在截止日前 N 天内

    # ---- 业务规律参数（开发文档第 13 节）----
    # 用户价值分层占比：高 / 中 / 低
    value_tier_ratio: tuple[float, float, float] = (0.10, 0.35, 0.55)
    # 每用户偏好分类数量范围 [min, max]
    preferred_category_range: tuple[int, int] = (1, 3)
    # 商品热度分层占比：热门 / 普通 / 冷门
    heat_level_ratio: tuple[float, float, float] = (0.15, 0.55, 0.30)

    # ---- 行为链概率（基础值，运行时再按渠道 / 用户 / 商品调整）----
    # 注意：为保证开发文档第 19 节漏斗 PV->Click->Collect->Cart->Buy 每一步单调递减，
    # 需 collect 概率 >= cart 概率 >= 实际购买概率。
    p_collect_given_click: float = 0.22
    p_cart_given_click: float = 0.18
    # 购买概率的全局乘子（乘在渠道 buy_base 之上，便于整体调高/调低购买量）
    buy_base_factor: float = 1.0
    cart_buy_boost: float = 2.5     # 加购后购买概率提升
    collect_buy_boost: float = 1.8  # 收藏后购买概率提升

    # ---- 订单状态分布（开发文档第 10 节：paid/cancelled/refunded）----
    order_status_ratio: tuple[float, float, float] = (0.82, 0.11, 0.07)

    # ---- 输出 ----
    output_dir: Path = field(default_factory=lambda: DEFAULT_RAW_DIR)


def load_config(
    scale: str | None = None,
    *,
    n_users: int | None = None,
    n_items: int | None = None,
    n_behaviors: int | None = None,
    random_state: int | None = None,
    output_dir: str | Path | None = None,
) -> DataGenConfig:
    """构建配置对象，优先级：CLI 参数 > 环境变量 > 规模预设 > 默认值。

    scale: low / standard / large 之一，作为"基线"，再被显式参数覆盖。
    """
    preset = dict(SCALE_PRESETS[scale]) if scale else {}

    def _env_int(name: str, default: int) -> int:
        val = os.environ.get(name)
        return int(val) if val else default

    users = n_users if n_users is not None else _env_int("DATA_USERS", preset.get("n_users", 2_000))
    items = n_items if n_items is not None else _env_int("DATA_ITEMS", preset.get("n_items", 1_000))
    behaviors = (
        n_behaviors
        if n_behaviors is not None
        else _env_int("DATA_BEHAVIORS", preset.get("n_behaviors", 100_000))
    )
    seed = random_state if random_state is not None else _env_int("DATA_RANDOM_STATE", RANDOM_STATE)

    out = Path(output_dir) if output_dir else DEFAULT_RAW_DIR

    return DataGenConfig(
        n_users=users,
        n_items=items,
        n_behaviors=behaviors,
        random_state=seed,
        output_dir=out,
    )
