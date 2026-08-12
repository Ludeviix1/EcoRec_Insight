"""日志体系：控制台 + 滚动文件双输出，统一格式。

使用方式：get_logger("module_name") 获取模块级 logger。
记录范围（Phase 后续扩展）：API request / ETL / 数据质量 / 模型训练 / 模型加载 / 推荐 / 延迟 / 错误。
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import get_settings

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()

    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)