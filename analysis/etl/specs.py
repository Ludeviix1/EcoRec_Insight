"""表规格定义（Phase 4）。

统一描述每张表的：源 CSV 列、必填字段、允许取值、数值边界、唯一键、
逻辑外键引用、时间规则、MySQL 目标表与入库列。

被 ``cleaning``（清洗）与 ``quality``（质检）与 ``etl``（加载）三个模块共用，
避免各写一套规格导致口径漂移。对应开发文档第 14 节（完整性/唯一性/一致性/
合法性/时间）与第 15 节（ETL）。

规格字段说明:
- columns:            源 CSV 列顺序（也是 DataFrame 列顺序）；
- required_fields:    非空字段（完整性检查）；
- allowed_values:     字段 -> 允许取值集合（合法性检查）；
- min_values:         字段 -> 下界（含，如 price >= 0）；
- gt_values:          字段 -> 严格下界（如 quantity > 0）；
- max_values:         字段 -> 上界（含）；
- datetime_fields:    需解析为 datetime 的字段（解析失败视为非法值）；
- unique_key:         去重主键（唯一性检查；None 表示按整行完全相同去重）；
- fk_refs:            字段 -> (参照表名, 参照表主键列)（一致性/逻辑外键检查）；
- mysql_table:        MySQL 目标表名；
- mysql_columns:      入库列顺序（与目标表一致，不含自增 id）；
- recompute_date_hour:是否用 event_time 重建 event_date/event_hour 冗余列。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---- 允许取值集合（开发文档第 9/10 节）----
BEHAVIOR_TYPES: tuple[str, ...] = ("pv", "click", "collect", "cart", "buy")
DEVICE_TYPES: tuple[str, ...] = ("mobile", "pc", "tablet")
CHANNELS: tuple[str, ...] = ("organic", "search", "ads", "campaign", "recommendation")
ORDER_STATUSES: tuple[str, ...] = ("paid", "cancelled", "refunded")

# MySQL 目标表（对应 sql/schema.sql 第 1~6 张核心表）
MYSQL_TABLES: tuple[str, ...] = (
    "categories", "users", "items", "user_behaviors", "orders", "order_items",
)


@dataclass(frozen=True)
class TableSpec:
    """单张表的 ETL 规格。"""

    name: str                                # 逻辑表名
    source_file: str                         # data/raw 下的源文件名
    processed_file: str                      # data/processed 下的输出文件名
    columns: tuple[str, ...]                 # 源列（顺序）
    mysql_table: str                         # MySQL 表名
    mysql_columns: tuple[str, ...]           # 入库列（顺序，不含 id）
    unique_key: str | None = None            # 唯一键
    required_fields: tuple[str, ...] = ()    # 完整性
    allowed_values: dict[str, tuple[str, ...]] = field(default_factory=dict)  # 合法性-枚举
    min_values: dict[str, float] = field(default_factory=dict)                # 合法性-下界(含)
    gt_values: dict[str, float] = field(default_factory=dict)                 # 合法性-严格下界
    max_values: dict[str, float] = field(default_factory=dict)                # 合法性-上界(含)
    datetime_fields: tuple[str, ...] = ()    # 合法性-时间解析
    fk_refs: dict[str, tuple[str, str]] = field(default_factory=dict)         # 一致性-逻辑外键
    nullable_fields: tuple[str, ...] = ()    # 入库允许 NULL 的字段
    recompute_date_hour: bool = False        # 用 event_time 重建冗余列


# ---------------------------------------------------------------------
# 六张核心表规格
# ---------------------------------------------------------------------
TABLE_SPECS: dict[str, TableSpec] = {
    # 维度层：分类（开发文档第 7 节）
    "categories": TableSpec(
        name="categories",
        source_file="categories.csv",
        processed_file="categories.csv",
        columns=("category_id", "category_name", "parent_id"),
        mysql_table="categories",
        mysql_columns=("category_id", "category_name", "parent_id"),
        unique_key="category_id",
        required_fields=("category_id", "category_name"),
        nullable_fields=("parent_id",),
        fk_refs={"parent_id": ("categories", "category_id")},
    ),
    # 维度层：用户（开发文档第 6 节）
    "users": TableSpec(
        name="users",
        source_file="users.csv",
        processed_file="users.csv",
        columns=("user_id", "age", "gender", "city", "register_time", "created_at", "updated_at"),
        mysql_table="users",
        mysql_columns=("user_id", "age", "gender", "city", "register_time", "created_at", "updated_at"),
        unique_key="user_id",
        required_fields=("user_id", "register_time", "created_at", "updated_at"),
        min_values={"age": 18.0},
        max_values={"age": 60.0},
        allowed_values={"gender": ("M", "F")},
        datetime_fields=("register_time", "created_at", "updated_at"),
    ),
    # 维度层：商品（开发文档第 8 节）
    "items": TableSpec(
        name="items",
        source_file="items.csv",
        processed_file="items.csv",
        columns=("item_id", "item_name", "category_id", "brand", "price", "stock", "status", "created_at"),
        mysql_table="items",
        mysql_columns=("item_id", "item_name", "category_id", "brand", "price", "stock", "status", "created_at"),
        unique_key="item_id",
        required_fields=("item_id", "item_name", "category_id", "price", "stock", "status", "created_at"),
        min_values={"price": 0.0, "stock": 0.0},
        allowed_values={"status": ("0", "1")},
        datetime_fields=("created_at",),
        fk_refs={"category_id": ("categories", "category_id")},
    ),
    # 原始事实层：用户行为（开发文档第 9 节）
    "user_behaviors": TableSpec(
        name="user_behaviors",
        source_file="user_behaviors.csv",
        processed_file="user_behaviors.csv",
        columns=(
            "behavior_id", "user_id", "item_id", "behavior_type",
            "event_time", "event_date", "event_hour", "device_type", "channel",
        ),
        mysql_table="user_behaviors",
        mysql_columns=(
            "behavior_id", "user_id", "item_id", "behavior_type",
            "event_time", "event_date", "event_hour", "device_type", "channel",
        ),
        unique_key="behavior_id",
        required_fields=("behavior_id", "user_id", "item_id", "behavior_type", "event_time",
                         "event_date", "event_hour", "device_type", "channel"),
        allowed_values={
            "behavior_type": BEHAVIOR_TYPES,
            "device_type": DEVICE_TYPES,
            "channel": CHANNELS,
        },
        min_values={"event_hour": 0.0},
        max_values={"event_hour": 23.0},
        datetime_fields=("event_time",),
        fk_refs={"user_id": ("users", "user_id"), "item_id": ("items", "item_id")},
        recompute_date_hour=True,
    ),
    # 原始事实层：订单（开发文档第 10 节）
    "orders": TableSpec(
        name="orders",
        source_file="orders.csv",
        processed_file="orders.csv",
        columns=("order_id", "user_id", "order_time", "total_amount", "status", "payment_method"),
        mysql_table="orders",
        mysql_columns=("order_id", "user_id", "order_time", "total_amount", "status", "payment_method"),
        unique_key="order_id",
        required_fields=("order_id", "user_id", "order_time", "total_amount", "status"),
        min_values={"total_amount": 0.0},
        allowed_values={"status": ORDER_STATUSES},
        datetime_fields=("order_time",),
        nullable_fields=("payment_method",),
        fk_refs={"user_id": ("users", "user_id")},
    ),
    # 原始事实层：订单明细（开发文档第 11 节）
    "order_items": TableSpec(
        name="order_items",
        source_file="order_items.csv",
        processed_file="order_items.csv",
        columns=("order_id", "item_id", "quantity", "unit_price", "amount"),
        mysql_table="order_items",
        mysql_columns=("order_id", "item_id", "quantity", "unit_price", "amount"),
        unique_key=None,                       # 无业务唯一键 -> 按整行去重
        required_fields=("order_id", "item_id", "quantity", "unit_price", "amount"),
        gt_values={"quantity": 0.0},
        min_values={"unit_price": 0.0, "amount": 0.0},
        fk_refs={
            "order_id": ("orders", "order_id"),
            "item_id": ("items", "item_id"),
        },
    ),
}

# ETL 处理顺序（维度先行：逻辑外键引用的表先入库）
ETL_ORDER: tuple[str, ...] = (
    "categories", "users", "items", "user_behaviors", "orders", "order_items",
)


def get_spec(table: str) -> TableSpec:
    try:
        return TABLE_SPECS[table]
    except KeyError:
        raise KeyError(f"unknown table spec: {table}") from None