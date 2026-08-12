"""数据生成入口脚本（Phase 3）。

运行方式（开发文档第 48 节）：
    python scripts/generate_data.py                      # 默认 low 规模
    python scripts/generate_data.py --scale standard     # 建议最终规模
    python scripts/generate_data.py --users 5000 --items 2000 --behaviors 200000

输出：data/raw/ 下 6 个 CSV + data_meta.json
不依赖 MySQL（入库由 Phase 4 ETL 完成）。
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 `analysis` 包可被导入
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.data_generation.generate import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
