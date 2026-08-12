"""行为与订单生成器（Phase 3 核心）。

算法：基于"会话（session）"生成行为链，保证行为与订单一致。

会话模型：
  一个用户在行为窗口内有若干次会话（数量由价值分层决定）。
  一次会话 = 在相近时间对 1~5 件商品的一系列交互。
  每件商品的交互按概率展开为行为链：
      PV (恒发生) -> Click (按渠道/偏好/热度概率) -> Collect / Cart (给定点击) -> Buy (给定点击)
  会话内所有 Buy 合并为一张订单（自然产生多商品同单 -> 关联规则有信号）。

业务规律（开发文档第 13 节）映射：
- 时间规律：会话时刻按小时权重（晚高峰）+ 周几权重（周末略高）抽取；
- 渠道差异：不同渠道 click_rate / buy_base 不同；
- 用户偏好：偏好分类的商品被浏览概率更高（recommendation 渠道加成最大）；
- 商品热度：曝光按热度权重（热门商品曝光远超占比，长尾）；
- 用户价值：高价值用户会话更多、购买概率更高、消费能力更强；
- 价格可负担性：高价商品对低消费能力用户购买概率衰减；
- 行为链：购买必须存在前置 Click（PV->Click->...->Buy）。

一致性约束：
- behavior_id 全局唯一；buy 行为与 order_items 一一对应（含 cancelled/refunded 订单）；
- event_time 落在 [用户注册后, 数据截止日] 内；
- 引用的 user_id / item_id 均来自已生成实体。

复杂度：O(会话数 × 平均交互数)，约等于 O(行为数)。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import DataGenConfig
from .constants import (
    CHANNEL_PROFILES,
    DEVICE_PROFILES,
    HOUR_WEIGHTS,
    PAYMENT_METHODS,
    RELATED_CATEGORIES,
    VALUE_TIERS,
    WEEKDAY_WEIGHTS,
)

# 保存到 CSV 的列顺序
BEHAVIOR_COLUMNS = [
    "behavior_id", "user_id", "item_id", "behavior_type",
    "event_time", "event_date", "event_hour", "device_type", "channel",
]
ORDER_COLUMNS = ["order_id", "user_id", "order_time", "total_amount", "status", "payment_method"]
ORDER_ITEM_COLUMNS = ["order_id", "item_id", "quantity", "unit_price", "amount"]

# 会话内平均行为数估计，用于由 n_behaviors 反推会话总数（近似，实际可能 ±20%）
EST_BEHAVIORS_PER_SESSION = 4.0
# 会话内最大交互商品数
MAX_INTERACTIONS_PER_SESSION = 5


def generate_behaviors_and_orders(
    rng: np.random.Generator,
    cfg: DataGenConfig,
    users: pd.DataFrame,
    items: pd.DataFrame,
    categories: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """生成 user_behaviors / orders / order_items 三张表。"""
    # ------------------------------------------------------------------
    # 1. 预构建商品索引，供按"分类 / 全局"加权抽取
    # ------------------------------------------------------------------
    item_ids = items["item_id"].to_numpy()
    item_prices = items["price"].to_numpy().astype(float)
    item_top = items["top_level"].to_numpy()
    item_heat = items["heat_level"].to_numpy()
    item_stock = items["stock"].to_numpy()
    item_status = items["status"].to_numpy()
    item_weight = items["exposure_weight"].to_numpy().astype(float)

    active_mask = item_status == 1
    active_idx = np.where(active_mask)[0]
    active_w = item_weight[active_idx]

    # top_level(一级分类名) -> (active 商品下标, 权重)
    top_to_items: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for top in np.unique(item_top):
        m = active_mask & (item_top == top)
        idx = np.where(m)[0]
        if len(idx) > 0:
            top_to_items[top] = (idx, item_weight[idx])

    # category_id -> top_level name（用户偏好存的是一级 category_id）
    top_rows = categories[categories["level"] == 1]
    cat_id_to_top = dict(zip(top_rows["category_id"], top_rows["category_name"]))

    # 渠道 / 设备抽取权重
    ch_names = list(CHANNEL_PROFILES.keys())
    ch_traffic = np.array([CHANNEL_PROFILES[c]["traffic_share"] for c in ch_names], dtype=float)
    dev_names = list(DEVICE_PROFILES.keys())
    dev_share = np.array([DEVICE_PROFILES[d]["share"] for d in dev_names], dtype=float)

    hour_w = np.asarray(HOUR_WEIGHTS, dtype=float)
    hour_w = hour_w / hour_w.sum()

    # ------------------------------------------------------------------
    # 2. 按价值分层把"目标会话总数"分配到每个用户（multinomial 保证总数精确）
    # ------------------------------------------------------------------
    n_users = len(users)
    tier = users["value_tier"].to_numpy()
    sess_w = np.array([VALUE_TIERS[t]["session_multiplier"] for t in tier], dtype=float)
    target_sessions = max(1, int(round(cfg.n_behaviors / EST_BEHAVIORS_PER_SESSION)))
    sess_counts = rng.multinomial(target_sessions, sess_w / sess_w.sum())

    # 每用户属性数组
    user_ids = users["user_id"].to_numpy()
    pref_cats = users["preferred_categories"].to_numpy()        # list[str] of category_id
    pref_channel = users["preferred_channel"].to_numpy()
    pref_device = users["preferred_device"].to_numpy()
    spending_power = users["spending_power"].to_numpy().astype(float)
    active_start = pd.to_datetime(users["active_start"]).dt.to_pydatetime()
    active_end = pd.to_datetime(users["active_end"]).dt.to_pydatetime()

    # ------------------------------------------------------------------
    # 3. 逐用户 -> 逐会话 -> 逐交互 生成行为链与订单
    # ------------------------------------------------------------------
    behavior_rows: list[tuple] = []
    order_rows: list[tuple] = []
    order_item_rows: list[tuple] = []

    bid_counter = 0
    oid_counter = 0

    for u in range(n_users):
        n_sess = int(sess_counts[u])
        if n_sess == 0:
            continue

        u_id = user_ids[u]
        u_tier = tier[u]
        u_power = spending_power[u]
        u_buy_mult = VALUE_TIERS[u_tier]["buy_multiplier"]
        # 偏好分类 -> top_level 名
        u_pref_tops = [cat_id_to_top[c] for c in pref_cats[u] if c in cat_id_to_top]

        a_start = active_start[u]
        a_end = active_end[u]
        session_times = _sample_session_times(rng, a_start, a_end, n_sess, hour_w)

        # 渠道 / 设备：用户偏好渠道/设备获得加成
        ch_w = ch_traffic.copy()
        ch_w[ch_names.index(pref_channel[u])] *= 1.6
        ch_w = ch_w / ch_w.sum()
        dev_w = dev_share.copy()
        dev_w[dev_names.index(pref_device[u])] *= 1.8
        dev_w = dev_w / dev_w.sum()

        for s in range(n_sess):
            session_dt = max(a_start, min(session_times[s], a_end - timedelta(minutes=100)))
            channel = str(rng.choice(ch_names, p=ch_w))
            device = str(rng.choice(dev_names, p=dev_w))
            ch_prof = CHANNEL_PROFILES[channel]
            device_evening = DEVICE_PROFILES[device]["is_evening_heavy"]

            n_inter = min(int(rng.geometric(0.45)), MAX_INTERACTIONS_PER_SESSION)
            session_buys: list[tuple] = []  # (item_idx, buy_time, price)
            bought_items: set[int] = set()
            first_top: str | None = None

            for k in range(n_inter):
                # --- 选品 ---
                item_idx, item_top_name = _pick_item(
                    rng, k, first_top, u_pref_tops, top_to_items,
                    active_idx, active_w, ch_prof["pref_match_boost"], item_top,
                )
                if first_top is None:
                    first_top = item_top_name

                price = float(item_prices[item_idx])
                heat = item_heat[item_idx]
                in_pref = item_top_name in u_pref_tops

                # --- 行为链时间锚点：每个交互在会话内错开 5~20 分钟 ---
                inter_offset = timedelta(minutes=int(rng.integers(5, 20)) * k)
                pv_time = session_dt + inter_offset

                # PV（恒发生）
                bid_counter += 1
                behavior_rows.append(_behavior_row(bid_counter, u_id, item_ids[item_idx], "pv", pv_time, device, channel))

                # Click
                pref_factor = 1.2 if in_pref else 1.0
                heat_factor = 1.1 if heat == "hot" else (0.9 if heat == "cold" else 1.0)
                click_prob = min(max(ch_prof["click_rate"] * pref_factor * heat_factor, 0.05), 0.95)
                if rng.random() < click_prob:
                    click_time = pv_time + timedelta(seconds=int(rng.integers(30, 120)))
                    bid_counter += 1
                    behavior_rows.append(_behavior_row(bid_counter, u_id, item_ids[item_idx], "click", click_time, device, channel))

                    # Collect / Cart（给定点击，独立）
                    if rng.random() < cfg.p_collect_given_click:
                        t = click_time + timedelta(seconds=int(rng.integers(60, 240)))
                        bid_counter += 1
                        behavior_rows.append(_behavior_row(bid_counter, u_id, item_ids[item_idx], "collect", t, device, channel))
                        collected = True
                    else:
                        collected = False
                    carted = False
                    if rng.random() < cfg.p_cart_given_click:
                        t = click_time + timedelta(seconds=int(rng.integers(60, 240)))
                        bid_counter += 1
                        behavior_rows.append(_behavior_row(bid_counter, u_id, item_ids[item_idx], "cart", t, device, channel))
                        carted = True

                    # Buy（给定点击；加购/收藏提升概率；价格可负担性衰减）
                    if item_idx not in bought_items and item_stock[item_idx] >= 1:
                        boost = cfg.cart_buy_boost if carted else (cfg.collect_buy_boost if collected else 1.0)
                        aff = _affordability(price, u_power)
                        # 渠道差异：不同渠道 buy_base 不同（ads 低、search 高）-> 渠道转化率有区分度
                        buy_prob = min(max(ch_prof["buy_base"] * cfg.buy_base_factor * u_buy_mult * aff * boost, 0.005), 0.75)
                        if rng.random() < buy_prob:
                            buy_time = click_time + timedelta(seconds=int(rng.integers(180, 900)))
                            buy_time = min(buy_time, a_end)
                            bid_counter += 1
                            behavior_rows.append(_behavior_row(bid_counter, u_id, item_ids[item_idx], "buy", buy_time, device, channel))
                            session_buys.append((item_idx, buy_time, price))
                            bought_items.add(item_idx)

            # --- 会话内购买合并为一张订单 ---
            if session_buys:
                oid_counter += 1
                order_id = f"O{oid_counter:08d}"
                order_time = min(bt for _, bt, _ in session_buys)
                status = str(rng.choice(
                    ["paid", "cancelled", "refunded"],
                    p=np.asarray(cfg.order_status_ratio, dtype=float) / np.sum(cfg.order_status_ratio),
                ))
                payment = str(rng.choice(PAYMENT_METHODS))
                total = 0.0
                for item_idx, _, iprice in session_buys:
                    qty = min(int(rng.geometric(0.5)), 3)
                    unit_price = round(iprice * (1.0 - float(rng.uniform(0.0, 0.10))), 2)
                    amount = round(qty * unit_price, 2)
                    total += amount
                    order_item_rows.append((order_id, item_ids[item_idx], qty, unit_price, amount))
                order_rows.append((order_id, u_id, order_time, round(total, 2), status, payment))

    behaviors = pd.DataFrame(behavior_rows, columns=BEHAVIOR_COLUMNS)
    orders = pd.DataFrame(order_rows, columns=ORDER_COLUMNS)
    order_items = pd.DataFrame(order_item_rows, columns=ORDER_ITEM_COLUMNS)
    return behaviors, orders, order_items


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------
def _behavior_row(bid: int, user_id: str, item_id: str, btype: str, dt: datetime, device: str, channel: str) -> tuple:
    """构造一条行为记录（含冗余的 event_date / event_hour 加速按日/按时统计）。"""
    return (
        f"B{bid:010d}", user_id, item_id, btype,
        dt.strftime("%Y-%m-%d %H:%M:%S"), dt.strftime("%Y-%m-%d"), dt.hour, device, channel,
    )


def _affordability(price: float, spending_power: float) -> float:
    """价格可负担性 -> [0.02, 1.0]。价格 <= 消费能力时为 1，超出则指数衰减。"""
    if price <= spending_power:
        return 1.0
    return max(0.02, math.exp(-(price - spending_power) / spending_power))


def _pick_item(
    rng: np.random.Generator,
    interaction_k: int,
    first_top: str | None,
    u_pref_tops: list[str],
    top_to_items: dict[str, tuple[np.ndarray, np.ndarray]],
    active_idx: np.ndarray,
    active_w: np.ndarray,
    pref_match_boost: float,
    item_top: np.ndarray,
) -> tuple[int, str]:
    """抽取一件商品（下标 + 其一级分类名）。

    选品逻辑：
    - 第 2+ 件交互有 50% 概率从首件的关联分类中选（制造同单跨分类购买）；
    - 否则按"偏好匹配概率"决定从偏好分类还是全局热门池选；
    - 偏好匹配概率受渠道 pref_match_boost 影响（recommendation 最高）。
    """
    # 关联分类聚类
    if interaction_k > 0 and first_top is not None and rng.random() < 0.5:
        related = RELATED_CATEGORIES.get(first_top, [first_top])
        cand_top = str(rng.choice(related))
        if cand_top in top_to_items:
            idxs, ws = top_to_items[cand_top]
            pos = rng.choice(idxs, p=ws / ws.sum())
            return int(pos), cand_top

    # 偏好匹配 vs 全局
    pref_match_prob = min(0.6 * pref_match_boost, 0.9)
    if u_pref_tops and rng.random() < pref_match_prob:
        chosen_top = str(rng.choice(u_pref_tops))
        if chosen_top in top_to_items:
            idxs, ws = top_to_items[chosen_top]
            pos = rng.choice(idxs, p=ws / ws.sum())
            return int(pos), chosen_top
        # 偏好分类暂无在架商品 -> 回退全局

    pos = rng.choice(active_idx, p=active_w / active_w.sum())
    return int(pos), str(item_top[int(pos)])


def _sample_session_times(
    rng: np.random.Generator,
    a_start: datetime,
    a_end: datetime,
    n_sessions: int,
    hour_w: np.ndarray,
) -> np.ndarray:
    """在该用户活跃窗口内抽取 n_sessions 个会话时刻（按周几权重 + 小时权重）。

    移动端夜间偏多、PC 白天偏多的差异通过调用方传入的 device 在外层体现，
    此处用基础小时权重统一抽取（已能体现晚高峰）。
    """
    start_date = a_start.date()
    end_date = a_end.date()
    n_days = (end_date - start_date).days + 1
    if n_days <= 0:
        n_days = 1

    # 按周几给每一天一个权重
    day_offsets = np.arange(n_days)
    day_weights = np.array([WEEKDAY_WEIGHTS[(start_date + timedelta(days=int(d))).weekday()] for d in day_offsets])
    day_weights = day_weights / day_weights.sum()

    chosen_offsets = rng.choice(day_offsets, size=n_sessions, p=day_weights)
    chosen_hours = rng.choice(24, size=n_sessions, p=hour_w)
    chosen_minutes = rng.integers(0, 60, size=n_sessions)

    times = np.empty(n_sessions, dtype=object)
    for i in range(n_sessions):
        dt = datetime.combine(start_date, datetime.min.time()) + timedelta(
            days=int(chosen_offsets[i]), hours=int(chosen_hours[i]), minutes=int(chosen_minutes[i])
        )
        if dt < a_start:
            dt = a_start
        elif dt > a_end:
            dt = a_end
        times[i] = dt
    return times
