"""Phase 5 基础分析入口脚本。

运行（开发文档第 48 节 / 第 49.3 节）：
    python scripts/run_analysis.py                          # 默认读取 data/processed，输出到 data/analysis
    python scripts/run_analysis.py --top-n 20

产物：
    data/analysis/user_scale.json      用户规模
    data/analysis/dau_wau_mau.json     DAU / WAU / MAU
    data/analysis/behavior.json        行为分析
    data/analysis/active_time.json     活跃时间
    data/analysis/gmv.json             GMV / 订单 / 客单价 / ARPU
    data/analysis/item_ranking.json    商品排行
    data/analysis/category_ranking.json 分类排行
    data/analysis/brand_ranking.json   品牌排行
    data/analysis/funnel.json          转化漏斗
    data/analysis/analysis_meta.json   运行记录
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from analysis.analysis.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())