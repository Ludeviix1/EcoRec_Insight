"""数据库连接：SQLAlchemy 2.x Engine / Session 工厂。

当前阶段（Phase 1）只建立连接能力，业务表在 Phase 2 通过 Base 建表。
设计：惰性连接 + pool_pre_ping，MySQL 未启动时应用仍可启动，health 接口不依赖数据库。
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类（Phase 2 建表时继承）。"""


def _create_engine():
    settings = get_settings()
    return create_engine(
        settings.mysql_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI 依赖：请求级 Session，自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_database() -> bool:
    """探测 MySQL 是否可连接（health 扩展 / 启动自检用）。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False