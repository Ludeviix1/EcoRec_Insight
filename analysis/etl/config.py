"""ETL 配置（Phase 4）。

读取 ``backend/.env`` 或项目根 ``.env``（内置极简 dotenv 解析，避免为 analysis
新增 python-dotenv 依赖），再叠加系统环境变量，最终可被 CLI 参数覆盖。
解析规则与 ``backend/app/core/config.py`` 保持一致：
MYSQL_HOST / MYSQL_PORT / MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ENV = _PROJECT_ROOT / "backend" / ".env"
_ROOT_ENV = _PROJECT_ROOT / ".env"

# 数据版本（开发文档第 E 节：dataset_version / generator_version / etl_version）
DATASET_VERSION = "v1"
ETL_VERSION = "1.0"


@dataclass(frozen=True)
class EtlConfig:
    """ETL 全部参数。"""

    raw_dir: Path = _PROJECT_ROOT / "data" / "raw"
    processed_dir: Path = _PROJECT_ROOT / "data" / "processed"
    interim_dir: Path = _PROJECT_ROOT / "data" / "interim"
    dataset_version: str = DATASET_VERSION
    etl_version: str = ETL_VERSION
    mode: str = "refresh"                # refresh=清空重载 / append=增量追加
    chunk_size: int = 5000               # 大文件批量读写批次
    mysql: bool = True                   # 是否加载到 MySQL

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "ecommerce_recommendation"

    @property
    def quality_report_path(self) -> Path:
        return self.interim_dir / "data_quality_report.json"

    @property
    def etl_meta_path(self) -> Path:
        return self.interim_dir / "etl_meta.json"


def _load_dotenv(*paths: Path) -> None:
    """极简 KEY=VALUE 解析（支持空行 / 注释 / 引号），不覆盖已有环境变量。"""
    for path in paths:
        if not Path(path).exists():
            continue
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _env(key: str, default):
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    return v


def load_etl_config(**overrides) -> EtlConfig:
    """构建 ETL 配置，优先级：CLI 参数 > 环境变量 > 默认值。"""
    _load_dotenv(_BACKEND_ENV, _ROOT_ENV)

    def _path(name: str, default: Path) -> Path:
        return Path(overrides[name]) if overrides.get(name) else Path(_env(name, str(default)))

    chunk_size = overrides.get("chunk_size") or int(_env("ETL_CHUNK_SIZE", "5000"))
    mode = overrides.get("mode") or _env("ETL_MODE", "refresh")
    mysql = overrides.get("mysql", True)
    if isinstance(mysql, str):
        mysql = mysql.lower() in ("1", "true", "yes")

    return EtlConfig(
        raw_dir=_path("raw_dir", _PROJECT_ROOT / "data" / "raw"),
        processed_dir=_path("processed_dir", _PROJECT_ROOT / "data" / "processed"),
        interim_dir=_path("interim_dir", _PROJECT_ROOT / "data" / "interim"),
        dataset_version=str(overrides.get("dataset_version") or _env("DATASET_VERSION", DATASET_VERSION)),
        etl_version=str(overrides.get("etl_version") or _env("ETL_VERSION", ETL_VERSION)),
        mode=mode,
        chunk_size=int(chunk_size),
        mysql=mysql,
        mysql_host=str(overrides.get("mysql_host") or _env("MYSQL_HOST", "127.0.0.1")),
        mysql_port=int(overrides.get("mysql_port") or _env("MYSQL_PORT", "3306")),
        mysql_user=str(overrides.get("mysql_user") or _env("MYSQL_USER", "root")),
        mysql_password=str(overrides.get("mysql_password") or _env("MYSQL_PASSWORD", "")),
        mysql_database=str(overrides.get("mysql_database") or _env("MYSQL_DATABASE", "ecommerce_recommendation")),
    )