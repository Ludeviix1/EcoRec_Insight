# sql 目录说明（Phase 2：建表）

> 以下"开发文档第 X 节"均指向项目最新版开发文档 `开发文档2.2.md`（如有更新版本以最新版为准）。

| 文件 | 内容 | 执行时机 |
|---|---|---|
| `schema.sql` | 12 张表：核心 6 张（users / categories / items / user_behaviors / orders / order_items，对应开发文档第 6~11 节）+ 扩展 6 张（user_profile / item_profile / user_segments / recommendation_results / model_predictions / model_metrics，对应文档第 5 节） | Phase 2 现在执行 |
| `indexes.sql` | 全部二级索引（文档第 46 节：user_id / item_id / event_time / event_date / behavior_type / category_id / order_id） | 建表后立即执行 |
| `views.sql` | 分析视图（DAU、GMV、漏斗等） | Phase 5 基础分析完成后生成 |
| `seed.sql` | 基础种子数据（分类表等） | Phase 3 数据生成器落地 |

## 手动建表步骤（Windows / Linux）

``` bash
# 1. 建库建表（含库不存在则创建，直接执行即可）
mysql -u root -p < sql/schema.sql

# 2. 建索引（需先执行 schema.sql）
mysql -u root -p < sql/indexes.sql
```

> 自动化（推荐，Phase 4 ETL 前置）：`python scripts/init_db.py [--reset]` 顺序执行 schema.sql + indexes.sql，连接参数读取 `backend/.env`。

## 注意事项

- 采用**逻辑外键**：不建物理 FOREIGN KEY 约束（百万级行为数据批量插入时物理外键严重拖慢写入），一致性由数据质量检查（Phase 4）保证，外键字段均建了索引。
- 推荐结果表的排名列使用 `reco_rank`（`rank` 是 MySQL 8.0 保留字，直接命名会建表失败）。
- `indexes.sql` 非幂等：重复执行会报"索引已存在"，忽略即可。
- 需要清空重建时：
  ``` bash
  mysql -u root -p -e "DROP DATABASE ecommerce_recommendation;"
  # 然后重新执行 schema.sql + indexes.sql
  ```
- 连接参数（库名/账号）与 `backend/.env` 保持一致：`ecommerce_recommendation` / 127.0.0.1:3306。