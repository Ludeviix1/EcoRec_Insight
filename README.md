# 电商用户行为分析与智能推荐平台

面向秋招求职展示的综合型 Python 数据分析、机器学习、推荐系统与数据应用平台。

项目目标：从一批原始数据出发，经过**数据生成 → 数据清洗 → ETL → 数据存储 → 数据质量 → 基础分析 → 深度业务分析 → 用户画像 → 用户分群 → 预测建模 → 推荐系统 → 推荐评估 → FastAPI → Vue3/ECharts → 测试 → 部署 → 项目文档**的完整数据闭环，最终形成真实可运行、可解释、可评估、可展示的数据应用。

> 完整开发规格见 `开发文档2.1.md`。

## 核心原则

- **P0（必须实现）**：数据生成/清洗/ETL/质量检查，全量分析体系，购买/流失预测，Popular/Item-CF/User-CF/Content/Hybrid 推荐，FastAPI + Vue3 + ECharts + Docker。
- **P1（加分项）**：用户价值预测、CTR 预测、多路召回 + LightGBM 排序、推荐多样性、Redis 缓存。
- **P2（仅设计，不实现代码）**：Kafka / Spark / Flink——只在 `docs/architecture.md` 中给出架构设计用于面试展示。

严格遵守：时间切分防数据泄漏（前 80% 训练 / 后 20% 测试）、`RANDOM_STATE = 42` 可复现、API 分层 `Router → Service → Repository → Database`、禁止伪实现（`pass` / mock 数据）。

## 目录结构

``` text
backend/    FastAPI 服务（app/core, models, schemas, routers, services, repositories, middleware, tests）
analysis/   数据分析链路（data_generation, cleaning, etl, quality, analysis, feature_engineering, models, recommendation）
data/       数据分层（raw / interim / processed / features）
sql/        MySQL 建表与索引脚本
frontend/   Vue3 + ECharts 前端（Phase 17 实现）
tests/      集成测试
docs/       架构与技术文档
scripts/    一键运行脚本（init_db / generate_data / run_etl / run_all）
docker/     Docker 编排资源
models/     训练产物（joblib 模型 + metadata）
```

## 当前进度

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | 需求和架构、仓库/目录、README | ✅ 完成 |
| 1 | Python + FastAPI 初始化：config / logging / database / health API | ✅ 完成 |
| 2 | MySQL 建表（6张核心表 + 主键/唯一键/外键逻辑/索引） | ✅ 完成 |
| 3 | 数据生成器（含业务规律模拟） | ✅ 完成 |
| 4+ | 详见 `开发文档2.1.md` 第 49 节 Phase 规划 | 待开发 |

## 快速开始（当前阶段）

``` bash
# 1. 创建虚拟环境（Windows）
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r backend/requirements.txt

# 3. 配置环境变量
copy backend\.env.example backend\.env

# 4. 生成模拟数据
python scripts/generate_data.py                    # 默认 low 规模 (2K 用户)
python scripts/generate_data.py --scale standard   # 标准规模 (10K 用户)

# 5. 启动后端
uvicorn backend.app.main:app --reload

# 6. 验证
curl http://127.0.0.1:8000/api/health
# 预期: {"code":0,"message":"success","data":{"status":"ok"}}
# 交互式文档: http://127.0.0.1:8000/docs

# 7. 运行测试
python -m pytest backend/tests -v               # 后端测试
python -m pytest tests/test_data_generation.py -v  # 数据生成测试
```

## 技术栈

Python 3.11+ · FastAPI · SQLAlchemy 2.x · MySQL 8.x · Pandas · scikit-learn · Vue3 · ECharts · Docker · pytest

（P1：LightGBM/XGBoost、Redis；P2 仅设计：Kafka/Spark/Flink）