"""pytest 路径配置：确保顶层 tests/ 可导入项目根的 ``analysis`` 包。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
