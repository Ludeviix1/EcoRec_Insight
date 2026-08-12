"""ETL CLI 入口（Phase 4）。

运行：``python -m analysis.etl.run --help``（或项目脚本 ``python scripts/run_etl.py``）
"""

from __future__ import annotations

import argparse
import sys

from .config import load_etl_config
from .pipeline import run_etl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 4 ETL: Raw CSV -> Schema Validation -> Cleaning -> Quality -> "
                    "Transformation -> Processed CSV -> MySQL（可重复执行）",
    )
    parser.add_argument("--raw-dir", type=str, default=None, help="原始数据目录（默认 data/raw）")
    parser.add_argument("--processed-dir", type=str, default=None, help="清洗输出目录（默认 data/processed）")
    parser.add_argument("--interim-dir", type=str, default=None, help="中间产物目录（默认 data/interim）")
    parser.add_argument("--dataset-version", type=str, default=None, help="数据版本（默认 v1）")
    parser.add_argument("--etl-version", type=str, default=None, help="ETL 版本（默认 1.0）")
    parser.add_argument("--mode", choices=["refresh", "append"], default=None,
                        help="refresh=清空重载（默认，幂等）；append=增量追加")
    parser.add_argument("--chunk-size", type=int, default=None, help="批量读写批次行数（默认 5000）")
    parser.add_argument("--skip-mysql", action="store_true", help="不写 MySQL，仅产出清洗数据 + 质检报告")

    args = parser.parse_args(argv)
    cfg = load_etl_config(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        interim_dir=args.interim_dir,
        dataset_version=args.dataset_version,
        etl_version=args.etl_version,
        mode=args.mode,
        chunk_size=args.chunk_size,
        mysql=not args.skip_mysql,
    )
    if cfg.mode == "append" and cfg.dataset_version == "v1":
        print("提示：append 模式建议显式指定 --dataset-version（如 v2）以避免版本混淆", file=sys.stderr)
    run_etl(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())