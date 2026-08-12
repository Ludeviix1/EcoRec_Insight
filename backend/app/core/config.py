"""应用配置：读取 `.env` 环境变量，统一管理数据库/Redis/推荐参数。

输入：backend/.env 或项目根目录 .env 文件 + 系统环境变量
输出：全局唯一 Settings 实例（get_settings()）
规则：禁止把密码写入代码，一律走 .env（已被 .gitignore 忽略）。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    APP_ENV: str = "development"

    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str = "ecommerce_recommendation"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    RECOMMEND_TOP_K: int = 10

    LOG_DIR: str = str(PROJECT_ROOT / "logs")
    LOG_LEVEL: str = "INFO"

    @property
    def mysql_url(self) -> str:
        """SQLAlchemy 连接串（mysql+pymysql）。"""
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"
        )

    model_config = SettingsConfigDict(
        env_file=[BACKEND_DIR / ".env", PROJECT_ROOT / ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()