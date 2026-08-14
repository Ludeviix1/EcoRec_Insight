"""Phase 18 数据库索引检查测试（开发文档第 49.16 节）。

校验 sql/indexes.sql 声明的全部二级索引已实际创建于 MySQL，
保证后端高频查询路径（user_id / item_id / event_time / category_id / order_id，
开发文档第 46 节）有索引兜底。MySQL 不可用时自动跳过，不阻塞无库环境回归。

运行：python -m pytest backend/tests/test_db_indexes.py -v
"""

import sys
from pathlib import Path

import pytest

# 将项目根目录加入 sys.path，复用 scripts/check_db_indexes 的索引解析（单一事实来源）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.app.core.config import get_settings  # noqa: E402

from scripts.check_db_indexes import expected_indexes  # noqa: E402


def _mysql_available() -> bool:
    try:
        import pymysql

        s = get_settings()
        conn = pymysql.connect(host=s.MYSQL_HOST, port=s.MYSQL_PORT,
                               user=s.MYSQL_USER, password=s.MYSQL_PASSWORD,
                               connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


MYSQL_OK = _mysql_available()
require_mysql = pytest.mark.skipif(not MYSQL_OK, reason="MySQL 服务不可用，跳过索引检查")


@require_mysql
def test_all_indexes_from_indexes_sql_exist():
    from sqlalchemy import text

    from backend.app.core.database import engine

    s = get_settings()
    expected = expected_indexes(_PROJECT_ROOT / "sql" / "indexes.sql")
    assert expected, "indexes.sql 未解析到任何 CREATE INDEX 语句"

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT TABLE_NAME, INDEX_NAME "
                "FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = :schema AND INDEX_NAME LIKE 'idx\\_%'"
            ),
            {"schema": s.MYSQL_DATABASE},
        ).fetchall()
    existing = {(str(r[0]).lower(), str(r[1]).lower()) for r in rows}

    missing = [e for e in expected if (e["table"], e["name"]) not in existing]
    assert not missing, (
        f"缺失索引 {len(missing)}/{len(expected)} 个："
        + ", ".join(f"{e['table']}.{e['name']}" for e in missing)
        + "。请执行 mysql -u root -p < sql/indexes.sql 或 python scripts/init_db.py"
    )


@require_mysql
def test_indexes_sql_declares_required_query_paths():
    """索引清单必须覆盖开发文档第 46 节要求的查询路径字段。"""
    expected = expected_indexes(_PROJECT_ROOT / "sql" / "indexes.sql")
    by_table = {t: {e["name"] for e in expected if e["table"] == t} for t in {e["table"] for e in expected}}

    assert any("user_id" in n or "user_time" in n for n in by_table.get("user_behaviors", set())), "缺 user_id 查询路径索引"
    assert any("item_time" in n for n in by_table.get("user_behaviors", set())), "缺 item_id 查询路径索引"
    assert by_table.get("orders", set()) and any("user_id" in n for n in by_table["orders"]), "缺 orders.user_id 索引"
    assert by_table.get("order_items", set()) and any(
        "item_id" in n for n in by_table["order_items"]
    ), "缺 order_items.item_id 索引"
    assert any("category" in n for n in by_table.get("items", set())), "缺 items.category_id 索引"
