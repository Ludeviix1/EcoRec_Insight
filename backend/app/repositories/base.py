"""仓库层公共工具：数据目录定位 / 常量。

Phase 16 数据访问约定（开发文档第 38 节 Router→Service→Repository→Database/Model）：
- 离线分析产物 data/analysis/*.json 由 run_analysis 生成，FastAPI 直接复用（README 第 85 行）；
- 维度数据（users/items/categories）、事实数据（user_behaviors/orders/order_items）
  读取 data/processed/*.csv（run_etl 产物，口径与 MySQL 一致）；
- 模型/推荐产物 data/prediction、data/churn、data/recommendation 读取模型与指标文件。

所有仓库读取结果使用 functools.lru_cache 做进程级缓存，避免每次请求重复读盘。
"""

from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

from ..core.database import engine
from ..core.exceptions import NotFoundError

# 项目根目录 = backend/ 的上级
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ANALYSIS_DIR = PROJECT_ROOT / "data" / "analysis"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PREDICTION_DIR = PROJECT_ROOT / "data" / "prediction"
CHURN_DIR = PROJECT_ROOT / "data" / "churn"
RECOMMENDATION_DIR = PROJECT_ROOT / "data" / "recommendation"

# 推荐算法白名单（与 analysis/recommendation 各实现一一对应）
RECOMMEND_ALGORITHMS: tuple[str, ...] = ("popular", "itemcf", "usercf", "content", "hybrid")

# 分析端点 -> data/analysis 文件名映射
ANALYSIS_FILE_MAP: dict[str, str] = {
    "rfm": "rfm",
    "lifecycle": "lifecycle",
    "cohort": "cohort",
    "path": "purchase_path",
    "purchase-path": "purchase_path",
    "channel": "channel",
    "price": "price",
    "association": "association",
    "segments": "user_segments",
    "user-segments": "user_segments",
    "findings": "findings",
    "device": "device",
    "item-lifecycle": "item_lifecycle",
    "active-time": "active_time",
    "behavior": "behavior",
    "gmv": "gmv",
    "user-scale": "user_scale",
    "dau-wau-mau": "dau_wau_mau",
    "funnel": "funnel",
    "retention": "retention",
    "item-ranking": "item_ranking",
    "category-ranking": "category_ranking",
    "brand-ranking": "brand_ranking",
    "user-profile": "user_profile",
    "item-profile": "item_profile",
}

ANALYSIS_NAMES: tuple[str, ...] = tuple(sorted(ANALYSIS_FILE_MAP.values()))


@lru_cache(maxsize=1)
def _read_json_cached(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise NotFoundError(message=f"数据文件不存在: {p.name}")
    import json

    return json.loads(p.read_text(encoding="utf-8"))


def read_json(rel_dir: Path, name: str) -> dict:
    """读 JSON 并缓存。name 为文件名（不含 .json）。"""
    return _read_json_cached(str(rel_dir / f"{name}.json"))


def mysql_count(table: str) -> int:
    """探测 MySQL 中某表行数；连接失败时返回 0（不阻塞 API）。"""
    try:
        with engine.connect() as conn:
            row = conn.execute(text(f"SELECT COUNT(*) AS c FROM `{table}`")).scalar()
            return int(row or 0)
    except Exception:
        return 0