# data 数据分层说明

| 目录 | 含义 | 内容 |
|---|---|---|
| `raw/` | 原始数据 | 数据生成器直接输出的模拟数据（users / items / user_behaviors / orders / order_items CSV） |
| `interim/` | 中间数据 | 清洗/ETL 过程中的中间产物、数据质量检查报告 `data_quality_report.json` |
| `processed/` | 加工数据 | 清洗去重后的最终数据集，供 MySQL 入库与全量分析使用 |
| `features/` | 特征数据 | 特征工程产出的 user / item / user-item / context 特征表（CSV/Parquet） |

约定：

- 数据目录内生成的业务文件全部被 `.gitignore` 忽略，仅保留 `.gitkeep`。
- 所有数据必须可复现：`RANDOM_STATE = 42`，生成脚本记录数据版本信息。
- 数据量可配置（默认见 `开发文档2.1.md` 第 12 节，低配电脑建议 用户 2,000 / 商品 1,000 / 行为 100,000 / 订单 10,000）。