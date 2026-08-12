"""核心生成器：分类 / 用户 / 商品（Phase 3）。

每个生成函数：
- 输入：``np.random.Generator`` + ``DataGenConfig``（+ 依赖的上游 DataFrame）
- 输出：``pd.DataFrame``（含 schema 列 + 生成期辅助列，保存前由 generate.py 裁剪）
- 复杂度：均为 O(n)，n 为对应实体数量

业务规律映射（开发文档第 13 节）：
- 用户：价值分层 + 偏好分类 + 偏好渠道/设备 + 注册时间分散（约 25% 落在行为窗口内为新用户）
- 商品：热度分层（长尾曝光）+ 按分类差异化的价格分布 + 品牌池
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import DataGenConfig
from .constants import (
    BRANDS_BY_CATEGORY,
    CATEGORY_TREE,
    CITIES,
    HEAT_LEVELS,
    ITEM_NAME_PREFIX,
    PRICE_DIST,
    VALUE_TIERS,
)

# 各表保存到 CSV 的 schema 列顺序（不含自增 id，入库时由 MySQL AUTO_INCREMENT 生成）
CATEGORY_COLUMNS = ["category_id", "category_name", "parent_id"]
USER_COLUMNS = ["user_id", "age", "gender", "city", "register_time", "created_at", "updated_at"]
ITEM_COLUMNS = ["item_id", "item_name", "category_id", "brand", "price", "stock", "status", "created_at"]


def _weighted_choice(rng: np.random.Generator, options: list, weights: list[float]) -> object:
    """按权重无放回抽取单个元素（权重自动归一化）。"""
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    return rng.choice(options, p=w)


def generate_categories(rng: np.random.Generator, cfg: DataGenConfig) -> pd.DataFrame:
    """生成分类表（一级 + 二级叶子分类）。

    算法：遍历 CATEGORY_TREE，一级分类 parent_id 为空，二级分类指向其一级 category_id。
    复杂度：O(分类总数)，与数据量无关。
    返回额外列 ``level``（1/2）与 ``top_level``（一级分类名）供下游使用。
    """
    rows = []
    seq = 0
    for top_name, subs in CATEGORY_TREE.items():
        seq += 1
        top_id = f"C{seq:03d}"
        rows.append({
            "category_id": top_id,
            "category_name": top_name,
            "parent_id": None,
            "level": 1,
            "top_level": top_name,
        })
        for sub_name in subs:
            seq += 1
            rows.append({
                "category_id": f"C{seq:03d}",
                "category_name": sub_name,
                "parent_id": top_id,
                "level": 2,
                "top_level": top_name,
            })
    return pd.DataFrame(rows)


def generate_users(rng: np.random.Generator, cfg: DataGenConfig) -> pd.DataFrame:
    """生成用户表 + 生成期辅助特征。

    业务规律：
    - 价值分层：按 value_tier_ratio 抽取 high/medium/low，决定活跃度/购买力；
    - 偏好分类：每用户 1~3 个一级分类（偏好驱动浏览，使推荐与渠道分析有信号）；
    - 注册时间：均匀分布在截止日前 365 天内，约 25% 落入 90 天行为窗口（新用户 cohort）；
    - 消费能力：按价值分层的基础额度 lognormal 扰动，影响高价商品可负担性。

    复杂度：O(n_users)。
    """
    n = cfg.n_users
    tiers = list(VALUE_TIERS.keys())
    tier_ratios = list(cfg.value_tier_ratio)

    # 价值分层
    value_tier = rng.choice(tiers, size=n, p=np.asarray(tier_ratios) / np.sum(tier_ratios))

    # 偏好分类（一级分类 id 列表，每用户 1~3 个，不重复）
    top_categories = list(CATEGORY_TREE.keys())
    top_cat_ids = {name: f"C{i + 1:03d}" for i, name in enumerate(top_categories)}
    pref_cat_ids = [_sample_preferred_categories(rng, top_categories, top_cat_ids, cfg) for _ in range(n)]

    # 偏好渠道 / 设备
    pref_channel = rng.choice(
        ["organic", "search", "ads", "campaign", "recommendation"],
        size=n,
        p=[0.22, 0.20, 0.18, 0.15, 0.25],
    )
    pref_device = rng.choice(["mobile", "pc", "tablet"], size=n, p=[0.65, 0.25, 0.10])

    # 消费能力（元）：按价值分层 base 做 lognormal 扰动
    spending_power = np.array(
        [VALUE_TIERS[t]["spending_power"] * rng.lognormal(mean=0.0, sigma=0.4) for t in value_tier]
    )

    # 注册时间：截止日前 365 天内均匀分布（自然产生约 25% 新用户落在 90 天窗口内）
    end = cfg.data_end_date
    reg_offset_days = rng.uniform(1, cfg.registration_window_days, size=n)  # 距截止日的天数
    register_time = np.array(
        [datetime(end.year, end.month, end.day) - timedelta(days=float(d)) for d in reg_offset_days]
    )
    # 偏移少量小时，避免全部 00:00
    reg_hour_offset = rng.integers(0, 24, size=n)
    register_time = np.array([t + timedelta(hours=int(h)) for t, h in zip(register_time, reg_hour_offset)])

    created_at = register_time  # 创建时间 = 注册时间

    # 用户基本信息
    age = np.clip(rng.normal(loc=30, scale=9, size=n).round().astype(int), 18, 60)
    gender = rng.choice(["M", "F"], size=n, p=[0.52, 0.48])
    city = rng.choice([c for c, _ in CITIES], size=n, p=np.asarray([w for _, w in CITIES]) / sum(w for _, w in CITIES))

    user_ids = [f"U{i + 1:06d}" for i in range(n)]

    df = pd.DataFrame({
        "user_id": user_ids,
        "age": age,
        "gender": gender,
        "city": city,
        "register_time": register_time,
        "created_at": created_at,
        "updated_at": register_time,
        # ---- 生成期辅助列（保存前裁剪）----
        "value_tier": value_tier,
        "preferred_categories": pref_cat_ids,   # list[str]
        "preferred_channel": pref_channel,
        "preferred_device": pref_device,
        "spending_power": spending_power.round(2),
    })

    # 行为窗口起止（新用户的活跃起点推迟到注册后）
    window_start = datetime(end.year, end.month, end.day) - timedelta(days=cfg.behavior_window_days)
    df["active_start"] = np.maximum(pd.to_datetime(register_time), pd.to_datetime(window_start)) + pd.Timedelta(hours=1)
    df["active_end"] = pd.to_datetime(end) + pd.Timedelta(hours=23, minutes=59)
    return df


def _sample_preferred_categories(
    rng: np.random.Generator,
    top_categories: list[str],
    top_cat_ids: dict[str, str],
    cfg: DataGenConfig,
) -> list[str]:
    """抽取 1~3 个不重复的一级偏好分类 id。"""
    lo, hi = cfg.preferred_category_range
    k = int(rng.integers(lo, hi + 1))
    chosen = rng.choice(top_categories, size=k, replace=False)
    return [top_cat_ids[c] for c in chosen]


def generate_items(
    rng: np.random.Generator,
    cfg: DataGenConfig,
    categories: pd.DataFrame,
) -> pd.DataFrame:
    """生成商品表 + 生成期辅助特征。

    业务规律：
    - 挂在二级（叶子）分类下，价格按一级分类的 LogNormal 分布（数码贵、食品便宜）；
    - 热度分层 hot/normal/cold，决定曝光权重（热门商品仅 15% 却拿约 50% 曝光）；
    - 品牌从分类品牌池抽取；少量商品下架(status=0)或零库存。

    复杂度：O(n_items)。
    """
    n = cfg.n_items
    leaf_cats = categories[categories["level"] == 2].reset_index(drop=True)
    leaf_ids = leaf_cats["category_id"].tolist()
    leaf_top = leaf_cats["top_level"].tolist()

    # 商品所属二级分类：均匀抽叶子分类（保证每个叶子都有商品）
    cat_idx = rng.integers(0, len(leaf_ids), size=n)
    category_id = np.asarray(leaf_ids)[cat_idx]
    top_level = np.asarray(leaf_top)[cat_idx]

    # 品牌：从该一级分类品牌池抽取
    brand = np.array([_weighted_choice(rng, BRANDS_BY_CATEGORY[t], [1.0] * len(BRANDS_BY_CATEGORY[t])) for t in top_level])

    # 价格：按一级分类 LogNormal 分布，clip 到区间
    price = np.empty(n)
    for i, t in enumerate(top_level):
        pd_params = PRICE_DIST[t]
        price[i] = float(np.clip(rng.lognormal(mean=pd_params["mu"], sigma=pd_params["sigma"]),
                                  pd_params["low"], pd_params["high"]))
    price = np.round(price, 2)

    # 热度分层
    heat_levels = list(HEAT_LEVELS.keys())
    heat_fracs = [HEAT_LEVELS[h]["fraction"] for h in heat_levels]
    heat = rng.choice(heat_levels, size=n, p=np.asarray(heat_fracs) / np.sum(heat_fracs))
    exposure_weight = np.array([HEAT_LEVELS[h]["exposure_weight"] for h in heat])

    # 库存：少数为 0（缺货），其余 1~500
    stock = rng.integers(0, 501, size=n)
    # 状态：约 5% 下架
    status = np.where(rng.random(n) < 0.05, 0, 1)

    # 商品名：前缀 + 品牌 + 随机型号
    names = []
    for i in range(n):
        sub_name = leaf_cats.iloc[cat_idx[i]]["category_name"]
        prefix_pool = ITEM_NAME_PREFIX.get(sub_name, ["商品"])
        prefix = rng.choice(prefix_pool)
        model = rng.integers(100, 1000)
        names.append(f"{brand[i]} {prefix} {model}")

    # 创建时间：截止日前 30~400 天（多数早于行为窗口，少量新品）
    end = cfg.data_end_date
    created_offset = rng.uniform(30, 400, size=n)
    created_at = np.array(
        [datetime(end.year, end.month, end.day) - timedelta(days=float(d)) for d in created_offset]
    )

    df = pd.DataFrame({
        "item_id": [f"I{i + 1:06d}" for i in range(n)],
        "item_name": names,
        "category_id": category_id,
        "brand": brand,
        "price": price,
        "stock": stock,
        "status": status,
        "created_at": created_at,
        # ---- 生成期辅助列 ----
        "top_level": top_level,
        "heat_level": heat,
        "exposure_weight": exposure_weight,
    })
    return df
