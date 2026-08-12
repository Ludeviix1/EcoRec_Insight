"""MySQL 数据仓库初始化脚本（Phase 2 蓝图落地 / Phase 4 ETL 前提）。

运行方式（开发文档第 48 节）：
    python scripts/init_db.py            # 建库建表 + 建索引（幂等）
    python scripts/init_db.py --reset    # 先删除数据库再重建（清空已有数据）

执行内容：
    sql/schema.sql   建库 + 12 张表（含唯一键约束）
    sql/indexes.sql  全部二级索引（开发文档第 46 节）

连接参数读取 backend/.env（MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD /
MYSQL_DATABASE），与后端配置一致，禁止把密码写进代码。
"""

import argparse
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 analysis 包可被导入
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pymysql  # noqa: E402

from analysis.etl.config import _env, _load_dotenv  # noqa: E402

SQL_DIR = _PROJECT_ROOT / "sql"


def _read_statements(path: Path) -> list[str]:
    """按 ';' 切分 SQL 文件（跳过 -- 注释），返回可独立执行的语句列表。"""
    statements: list[str] = []
    buf: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buf).strip())
            buf = []
    return [s for s in statements if s]


def _execute(conn: pymysql.connections.Connection, statements: list[str]) -> None:
    with conn.cursor() as cur:
        for sql in statements:
            cur.execute(sql)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化 MySQL 数据仓库（schema.sql + indexes.sql）")
    parser.add_argument("--reset", action="store_true", help="先 DROP DATABASE 再重建（会清空现有数据）")
    args = parser.parse_args(argv)

    _load_dotenv(_PROJECT_ROOT / "backend" / ".env", _PROJECT_ROOT / ".env")
    host = _env("MYSQL_HOST", "127.0.0.1")
    port = int(_env("MYSQL_PORT", "3306"))
    user = _env("MYSQL_USER", "root")
    password = _env("MYSQL_PASSWORD", "")
    database = _env("MYSQL_DATABASE", "ecommerce_recommendation")

    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password,
                               charset="utf8mb4", autocommit=True, connect_timeout=10)
    except Exception as exc:  # noqa: BLE001
        print(f"无法连接 MySQL（{host}:{port}）：{exc}", file=sys.stderr)
        return 1

    schema_path = SQL_DIR / "schema.sql"
    indexes_path = SQL_DIR / "indexes.sql"
    if not schema_path.exists() or not indexes_path.exists():
        print(f"缺少 SQL 脚本: {schema_path} / {indexes_path}", file=sys.stderr)
        return 1

    try:
        if args.reset:
            print(f"[1/2] DROP DATABASE IF EXISTS {database}")
            _execute(conn, [f"DROP DATABASE IF EXISTS `{database}`"])
        statements = _read_statements(schema_path)
        print(f"[1/2] 执行 {schema_path.name}（{len(statements)} 条语句）")
        _execute(conn, statements)
        index_statements = _read_statements(indexes_path)
        print(f"[2/2] 执行 {indexes_path.name}（{len(index_statements)} 条语句，重复执行报错可忽略）")
        _execute(conn, index_statements)
        print(f"完成：数据库 {database} 表结构与索引就绪")
    except Exception as exc:  # noqa: BLE001
        print(f"初始化失败：{exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())