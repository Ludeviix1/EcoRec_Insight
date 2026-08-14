"""Phase 5 基础分析配置。

只读取 processed CSV，不需要 MySQL。目录默认指向项目 data/ 分层，
支持环境变量 / CLI 覆盖（与 ``analysis.etl.config`` 风格一致）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 分析版本（开发文档第 E 节 / 第 47 节：可复现性）
ANALYSIS_VERSION = "1.0"


@dataclass(frozen=True)
class AnalysisConfig:
    """基础分析全部参数。"""

    processed_dir: Path = _PROJECT_ROOT / "data" / "processed"
    interim_dir: Path = _PROJECT_ROOT / "data" / "interim"
    output_dir: Path = _PROJECT_ROOT / "data" / "analysis"
    analysis_version: str = ANALYSIS_VERSION
    top_n: int = 10          # 排行 TOP N 默认值

    @property
    def output_meta_path(self) -> Path:
        return self.output_dir / "analysis_meta.json"


def load_analysis_config(**overrides) -> AnalysisConfig:
    """构建分析配置，优先级：CLI 参数 > 环境变量 > 默认值。"""

    def _path(name: str, default: Path) -> Path:
        return Path(overrides[name]) if overrides.get(name) else Path(os.environ.get(name, str(default)))

    top_n = overrides.get("top_n") or int(os.environ.get("ANALYSIS_TOP_N", "10"))
    version = overrides.get("analysis_version") or os.environ.get("ANALYSIS_VERSION", ANALYSIS_VERSION)

    return AnalysisConfig(
        processed_dir=_path("processed_dir", _PROJECT_ROOT / "data" / "processed"),
        interim_dir=_path("interim_dir", _PROJECT_ROOT / "data" / "interim"),
        output_dir=_path("output_dir", _PROJECT_ROOT / "data" / "analysis"),
        analysis_version=str(version),
        top_n=int(top_n),
    )
