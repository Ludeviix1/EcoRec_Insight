"""Phase 5 基础分析公共工具。

提供：
- 常量：行为类型 / 渠道 / 设备 / 订单状态（复用 ``analysis.etl.specs`` 的口径）；
- ``safe_div``：除法防除零（开发文档第 18.2 节）；
- ``load_processed``：读取 data/processed 清洗后 CSV（供后续模块直接消费）；
- ``write_json``：结构化结果落盘为 JSON。

所有工具只依赖 pandas，不依赖 MySQL，保证可单测。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---- 允许取值集合（与 analysis/etl/specs.py 保持一致）----
BEHAVIOR_TYPES: tuple[str, ...] = ("pv", "click", "collect", "cart", "buy")
DEVICE_TYPES: tuple[str, ...] = ("mobile", "pc", "tablet")
CHANNELS: tuple[str, ...] = ("organic", "search", "ads", "campaign", "recommendation")
ORDER_STATUSES: tuple[str, ...] = ("paid", "cancelled", "refunded")

# 转化漏斗阶段顺序（开发文档第 19 节）
FUNNEL_STAGES: tuple[str, ...] = ("pv", "click", "collect", "cart", "buy")


def safe_div(num: float | int | None, den: float | int | None, *, scale: int = 4) -> float:
    """除法并防止除零：分母为空/0 时返回 0.0（开发文档第 18.2 节）。

    参数:
        num: 分子
        den: 分母
        scale: 结果保留小数位
    """
    if num is None or den is None:
        return 0.0
    try:
        den = float(den)
        num = float(num)
    except (TypeError, ValueError):
        return 0.0
    if den == 0.0:
        return 0.0
    return round(num / den, scale)


def load_processed(processed_dir: Path | str, name: str) -> pd.DataFrame:
    """读取 data/processed 下清洗后的 CSV（UTF-8 with BOM）。

    参数:
        processed_dir: data/processed 目录
        name: 表名（如 "users" / "user_behaviors"），文件名为 ``<name>.csv``
    """
    path = Path(processed_dir) / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"processed 数据缺失: {path}")
    return pd.read_csv(path, encoding="utf-8-sig")


def write_json(path: Path | str, data: dict | list) -> None:
    """把结构化结果写入 JSON 文件（UTF-8、缩进、不转义中文）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
