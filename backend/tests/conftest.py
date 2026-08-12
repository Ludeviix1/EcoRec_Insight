"""pytest 路径配置：确保无论从哪个目录运行，backend 均加入 sys.path。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))