"""ETL 入口脚本（Phase 4）。

运行方式（开发文档第 48 节）：
    python scripts/run_etl.py                          # 默认：清洗 + 质检 + 入库（refresh 幂等）
    python scripts/run_etl.py --skip-mysql             # 仅清洗 + 质检，不写 MySQL
    python scripts/run_etl.py --mode append --dataset-version v2

输出：data/processed/ 6 张清洗 CSV、data/interim/data_quality_report.json、
     data/interim/etl_meta.json、（可选）MySQL 6 张核心表。
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 `analysis` 包可被导入
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.etl.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())