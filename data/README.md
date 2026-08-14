# data 数据分层说明

> 以下"开发文档第 X 节"均指向项目最新版开发文档 `开发文档2.2.md`（如有更新版本以最新版为准）。

| 目录 | 含义 | 内容 |
|---|---|---|
| `raw/` | 原始数据（Phase 3 产物，只读） | 数据生成器直接输出的模拟数据（users / items / user_behaviors / orders / order_items CSV）+ `data_meta.json` |
| `interim/` | 中间数据（Phase 4 产物） | 数据质量报告 `data_quality_report.json`、ETL 运行记录 `etl_meta.json` |
| `processed/` | 加工数据（Phase 4 产物） | 清洗去重后的最终数据集（6 张 CSV），供 MySQL 入库与 Phase 5+ 全量分析使用 |
| `analysis/` | 分析结果（Phase 5 产物） | 基础分析结构化 JSON（用户规模 / DAU·WAU·MAU / 行为 / 活跃时间 / GMV / 商品·分类·品牌排行 / 漏斗），供 FastAPI 直接复用 |
| `features/` | 特征数据 | 特征工程产出的 user / item / user-item / context 特征表（CSV/Parquet） |

约定：

- 数据目录内生成的业务文件全部被 `.gitignore` 忽略，仅保留 `.gitkeep`。
- 所有数据必须可复现：`RANDOM_STATE = 42`，生成脚本记录数据版本信息。
- 数据量可配置（默认见 `开发文档2.2.md` 第 12 节，低配电脑建议 用户 2,000 / 商品 1,000 / 行为 100,000 / 订单 10,000）。
- ETL（Phase 4）：`python scripts/run_etl.py` 把 `raw/` 清洗为 `processed/` 并写出质检报告，`refresh` 模式自动清空 MySQL 核心表重载，重复运行不会产生重复订单/行为。
- 基础分析（Phase 5）：`python scripts/run_analysis.py` 读取 `processed/`，把结果输出到 `analysis/` 下的 JSON 文件，并记录 `analysis_meta.json`。
