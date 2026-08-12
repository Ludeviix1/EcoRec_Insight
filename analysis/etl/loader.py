"""MySQL 批量加载器（Phase 4）。

对应开发文档第 15 节 ETL 要求：
- 批量插入：pymysql.executemany + autocommit，每次 chunk_size 行，禁止逐行写库；
- 可重复执行：refresh 模式先 TRUNCATE 六张核心表，再 INSERT IGNORE（唯一键兜底，
  重复运行不会产生重复订单/行为）；
- 顺序入库：ETL_ORDER（维度 -> 事实），保证逻辑外键始终成立；
- 无物理外键：一致性由 Phase 4 数据质量检查保证。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import pymysql

from .config import EtlConfig
from .specs import MYSQL_TABLES, TableSpec

logger = logging.getLogger("etl.loader")


class MySQLLoader:
    """封装 MySQL 连接与批量写入。"""

    def __init__(self, cfg: EtlConfig):
        self._conn = pymysql.connect(
            host=cfg.mysql_host,
            port=cfg.mysql_port,
            user=cfg.mysql_user,
            password=cfg.mysql_password,
            database=cfg.mysql_database,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=10,
        )

    def close(self) -> None:
        if self._conn is not None and self._conn.open:
            self._conn.close()

    def __enter__(self) -> "MySQLLoader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _execute(self, sql: str, args=None) -> None:
        with self._conn.cursor() as cur:
            cur.execute(sql, args or ())

    def _execute_many(self, sql: str, rows) -> None:
        if not rows:
            return
        with self._conn.cursor() as cur:
            cur.executemany(sql, rows)

    # ----------------------------------------------------------------
    # 幂等
    # ----------------------------------------------------------------
    def truncate(self, tables: tuple[str, ...] = MYSQL_TABLES) -> None:
        """清空核心表（refresh 模式入口）。逻辑外键无物理约束，可直接 TRUNCATE。"""
        self._execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in tables:
            self._execute(f"TRUNCATE TABLE `{table}`")
        self._execute("SET FOREIGN_KEY_CHECKS = 1")
        logger.info("truncated tables: %s", ", ".join(tables))

    # ----------------------------------------------------------------
    # 写入
    # ----------------------------------------------------------------
    def bulk_insert(self, spec: TableSpec, rows: list[tuple], chunk_size: int) -> int:
        """批量插入（INSERT IGNORE：唯一键冲突自动跳过，保证幂等不重复）。"""
        if not rows:
            return 0
        cols = ", ".join(f"`{c}`" for c in spec.mysql_columns)
        placeholders = ", ".join(["%s"] * len(spec.mysql_columns))
        sql = f"INSERT IGNORE INTO `{spec.mysql_table}` ({cols}) VALUES ({placeholders})"
        for i in range(0, len(rows), chunk_size):
            self._execute_many(sql, rows[i:i + chunk_size])
        return len(rows)

    def update(self, table: str, set_col: str, key_col: str, pairs: list[tuple]) -> int:
        """按主键更新（用于 Transformation 阶段修正订单金额）。"""
        if not pairs:
            return 0
        sql = f"UPDATE `{table}` SET `{set_col}` = %s WHERE `{key_col}` = %s"
        self._execute_many(sql, pairs)
        return len(pairs)

    # ----------------------------------------------------------------
    # 校验
    # ----------------------------------------------------------------
    def count(self, table: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM `{table}`")
            return int(cur.fetchone()[0])

    def table_counts(self) -> dict[str, int]:
        return {t: self.count(t) for t in MYSQL_TABLES}

    @contextmanager
    def cursor(self):
        with self._conn.cursor() as cur:
            yield cur