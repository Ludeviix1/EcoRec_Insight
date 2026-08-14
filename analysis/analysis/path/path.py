"""用户购买路径分析（开发文档第 24 节）。

口径（明确定义）：
- 会话切分：同一用户相邻行为时间间隔超过 ``session_gap_minutes``（默认 30 分钟）
  视为一次新会话；
- 路径构造：会话内按时间排序的行为类型序列，**压缩连续重复**（如 pv,pv,click,pv
  → pv,click,pv），不伪造不存在的页面类型；
- 只有真实存在的 5 种行为类型（pv/click/collect/cart/buy），数据中无 search，
  因此**不会生成"搜索路径"**；
- 指标：路径数量（去重路径数）、每条路径的会话数与用户数、最终购买率
  （该路径中最终存在 buy 的会话占比）。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..base import FUNNEL_STAGES, safe_div

# 已知行为类型（用于路径令牌）
PATH_TOKENS: tuple[str, ...] = FUNNEL_STAGES


@dataclass(frozen=True)
class PathConfig:
    """购买路径分析配置。"""

    session_gap_minutes: int = 30     # 会话切分阈值（分钟）
    top_n: int = 10                   # 输出路径数


def purchase_path_analysis(
    behaviors: pd.DataFrame,
    cfg: PathConfig | None = None,
) -> dict:
    """按会话构造用户行为路径并统计。

    参数:
        behaviors: user_behaviors.csv，至少含 user_id / event_time / behavior_type
        cfg: 路径分析配置（会话阈值 / TOP N）

    返回:
        dict:
        - definition: 会话切分与路径构造口径
        - config: 实际使用参数
        - total_sessions / total_users / distinct_paths
        - top_paths: list[{"path","sessions","users","buy_sessions","final_buy_rate"}]
        - longest_path: 最长的路径（token 数）
    """
    cfg = cfg or PathConfig()
    gap = pd.Timedelta(minutes=cfg.session_gap_minutes)

    df = behaviors[["user_id", "event_time", "behavior_type"]].copy()
    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    df = df.dropna(subset=["event_time"])
    df = df.sort_values(["user_id", "event_time"]).reset_index(drop=True)

    # 会话 id：与上一条（同用户）间隔 > gap 视为新会话
    prev_user = df["user_id"] != df["user_id"].shift(1)
    gap_since_prev = df["event_time"] - df["event_time"].shift(1)
    new_session = prev_user | (gap_since_prev > gap)
    df["session_id"] = new_session.cumsum()

    window = 10 ** 9  # 全量窗口
    seqs = []
    for sid, g in df.groupby("session_id"):
        seq = _compress(list(g["behavior_type"]))
        seqs.append({
            "session_id": sid,
            "user_id": g["user_id"].iloc[0],
            "path": seq,
            "buy": int(("buy" in g["behavior_type"].values)),
        })
    sessions = pd.DataFrame(seqs)

    if sessions.empty:
        return {
            "definition": _definition(cfg),
            "config": _config(cfg),
            "total_sessions": 0,
            "total_users": 0,
            "distinct_paths": 0,
            "top_paths": [],
            "longest_path": {"tokens": 0, "path": ""},
        }

    sessions["path_str"] = sessions["path"].apply("→".join)

    grouped = (
        sessions.groupby("path_str")
        .agg(sessions=("session_id", "count"), users=("user_id", "nunique"),
             buy_sessions=("buy", "sum"))
        .reset_index()
    )
    grouped["final_buy_rate"] = [
        safe_div(b, s) for b, s in zip(grouped["buy_sessions"], grouped["sessions"])
    ]
    grouped = grouped.sort_values(["sessions"], ascending=False)

    top = grouped.head(cfg.top_n)
    top_paths = [
        {
            "path": r["path_str"],
            "sessions": int(r["sessions"]),
            "users": int(r["users"]),
            "buy_sessions": int(r["buy_sessions"]),
            "final_buy_rate": round(float(r["final_buy_rate"]), 4),
        }
        for r in top.to_dict("records")
    ]

    longest = sessions.loc[sessions["path"].apply(len).idxmax()]
    longest_users = grouped.loc[grouped["path_str"] == longest["path_str"], "users"].max()
    return {
        "definition": _definition(cfg),
        "config": _config(cfg),
        "total_sessions": int(len(sessions)),
        "total_users": int(sessions["user_id"].nunique()),
        "distinct_paths": int(grouped.shape[0]),
        "top_paths": top_paths,
        "longest_path": {
            "tokens": int(len(longest["path"])),
            "users": int(longest_users) if longest_users == longest_users else 0,
            "path": longest["path_str"],
        },
    }


def _compress(seq: list[str]) -> list[str]:
    """压缩连续重复行为类型，保留首次出现之间的顺序。"""
    out: list[str] = []
    for t in seq:
        if not out or out[-1] != t:
            out.append(t)
    return out


def _definition(cfg: PathConfig) -> str:
    return (
        f"会话切分：同一用户相邻行为间隔超过 {cfg.session_gap_minutes} 分钟视为新会话；"
        "路径=会话内按时间排序的行为类型序列（压缩连续重复）；"
        "数据仅含 pv/click/collect/cart/buy 五种行为，不含 search，不构造搜索路径；"
        "最终购买率=该路径中最终存在 buy 的会话占比。"
    )


def _config(cfg: PathConfig) -> dict:
    return {
        "session_gap_minutes": cfg.session_gap_minutes,
        "top_n": cfg.top_n,
        "behavior_tokens": list(PATH_TOKENS),
    }