"""数据库索引检查脚本（Phase 18：数据库索引检查 / 性能优化）。

检查 sql/indexes.sql 中声明的全部二级索引是否已实际存在于 MySQL，
与后端查询路径（开发文档第 46 节）保持一致，防止索引缺失拖慢线上查询。

运行方式：
    python scripts/check_db_indexes.py                # 检查并退出（0=全部存在，1=有缺失）
    python scripts/check_db_indexes.py -v             # 详细列出每个索引的状态

连接参数读取 backend/.env（MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD /
MYSQL_DATABASE），与后端配置一致，禁止把密码写进代码。
"""

import argparse
import re
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 analysis 包可被导入
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pymysql  # noqa: E402

from analysis.etl.config import _env, _load_dotenv  # noqa: E402

SQL_DIR = _PROJECT_ROOT / "sql"
# 匹配 sql/indexes.sql 里的 CREATE INDEX idx_name ON table (...)
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+`?(?P<name>idx_\w+)`?\s+ON\s+`?(?P<table>\w+)`?",
    re.IGNORECASE,
)


def expected_indexes(indexes_sql: Path) -> list[dict[str, str]]:
    """解析 indexes.sql，返回 [{name, table}] 期望索引清单（保持与 SQL 同步）。"""
    out: list[dict[str, str]] = []
    for line in indexes_sql.read_text(encoding="utf-8").splitlines():
        m = _CREATE_INDEX_RE.search(line)
        if m:
            out.append({"name": m.group("name").lower(), "table": m.group("table").lower()})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 MySQL 索引是否与 sql/indexes.sql 一致")
    parser.add_argument("-v", "--verbose", action="store_true", help="逐条列出每个索引状态")
    args = parser.parse_args(argv)

    _load_dotenv(_PROJECT_ROOT / "backend" / ".env", _PROJECT_ROOT / ".env")
    host = _env("MYSQL_HOST", "127.0.0.1")
    port = int(_env("MYSQL_PORT", "3306"))
    user = _env("MYSQL_USER", "root")
    password = _env("MYSQL_PASSWORD", "")
    database = _env("MYSQL_DATABASE", "ecommerce_recommendation")

    indexes_path = SQL_DIR / "indexes.sql"
    if not indexes_path.exists():
        print(f"缺少 SQL 脚本: {indexes_path}", file=sys.stderr)
        return 1

    expected = expected_indexes(indexes_path)
    if not expected:
        print(f"未从 {indexes_path.name} 解析到任何 CREATE INDEX 语句", file=sys.stderr)
        return 1

    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password,
                               database=database, charset="utf8mb4", autocommit=True,
                               connect_timeout=10)
    except Exception as exc:  # noqa: BLE001
        print(f"无法连接 MySQL（{host}:{port}/{database}）：{exc}", file=sys.stderr)
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT TABLE_NAME, INDEX_NAME "
                "FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA=%s AND INDEX_NAME LIKE 'idx\\_%%'",
                (database,),
            )
            existing = {(row[0].lower(), row[1].lower()) for row in cur.fetchall()}
    finally:
        conn.close()

    missing = [e for e in expected if (e["table"], e["name"]) not in existing]

    if args.verbose:
        for e in expected:
            ok = (e["table"], e["name"]) in existing
            print(f"[{'OK ' if ok else 'MISSING'}] {e['table']}.{e['name']}")
        print()
    if missing:
        print(f"存在 {len(missing)} 个缺失索引（共声明 {len(expected)} 个）：")
        for e in missing:
            print(f"  - {e['table']}.{e['name']}")
        print(f"可执行 mysql -u root -p < sql/indexes.sql 补建，或运行 python scripts/init_db.py")
        return 1
    print(f"OK：数据库 {database} 的 {len(expected)} 个二级索引全部存在。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
