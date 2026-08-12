-- =====================================================================
-- 电商用户行为分析与智能推荐平台 - 建表脚本 (Phase 2)
-- 执行方式: mysql -u root -p < sql/schema.sql
-- 数据库:   ecommerce_recommendation (utf8mb4)
-- 说明:
--   1. 主键 / 唯一键在表内定义（表级约束），二级查询索引统一放 indexes.sql。
--   2. 采用逻辑外键设计：不建立物理 FOREIGN KEY（百万级行为数据批量插入时
--      物理外键会显著拖慢写入），一致性由应用层数据质量检查保证 + 索引加速。
--   3. 核心 6 表对应开发文档第 6~11 节；扩展 6 表对应第 5 节"建议增加"，
--      用于画像 / 分群 / 推荐结果 / 模型预测落库。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS ecommerce_recommendation
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ecommerce_recommendation;

-- ---------------------------------------------------------------------
-- 一、核心表
-- ---------------------------------------------------------------------

-- 1. 用户表 users（开发文档第 6 节）
CREATE TABLE IF NOT EXISTS users (
  id            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  user_id       VARCHAR(32)  NOT NULL                COMMENT '用户ID（对外业务标识）',
  age           INT          NULL                    COMMENT '年龄',
  gender        VARCHAR(16)  NULL                    COMMENT '性别',
  city          VARCHAR(64)  NULL                    COMMENT '城市',
  register_time DATETIME     NOT NULL                COMMENT '注册时间',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 2. 分类表 categories（开发文档第 7 节）
CREATE TABLE IF NOT EXISTS categories (
  id            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  category_id   VARCHAR(32)  NOT NULL                COMMENT '分类ID',
  category_name VARCHAR(128) NOT NULL                COMMENT '分类名称',
  parent_id     VARCHAR(32)  NULL                    COMMENT '父分类ID（一级分类为 NULL）',
  PRIMARY KEY (id),
  UNIQUE KEY uk_categories_category_id (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='分类表';

-- 3. 商品表 items（开发文档第 8 节）
CREATE TABLE IF NOT EXISTS items (
  id          BIGINT        NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  item_id     VARCHAR(32)   NOT NULL                COMMENT '商品ID',
  item_name   VARCHAR(255)  NOT NULL                COMMENT '商品名称',
  category_id VARCHAR(32)   NOT NULL                COMMENT '所属分类ID',
  brand       VARCHAR(128)  NULL                    COMMENT '品牌',
  price       DECIMAL(10,2) NOT NULL                COMMENT '单价',
  stock       INT           NOT NULL DEFAULT 0      COMMENT '库存',
  status      TINYINT       NOT NULL DEFAULT 1      COMMENT '状态：1=上架 0=下架',
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_items_item_id (item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品表';

-- 4. 用户行为表 user_behaviors（开发文档第 9 节）
CREATE TABLE IF NOT EXISTS user_behaviors (
  id            BIGINT      NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  behavior_id   VARCHAR(64) NOT NULL                COMMENT '行为ID（唯一）',
  user_id       VARCHAR(32) NOT NULL                COMMENT '用户ID',
  item_id       VARCHAR(32) NOT NULL                COMMENT '商品ID',
  behavior_type VARCHAR(16) NOT NULL                COMMENT '行为类型：pv/click/collect/cart/buy',
  event_time    DATETIME    NOT NULL                COMMENT '行为时间',
  event_date    DATE        NOT NULL                COMMENT '行为日期（冗余，加速按日统计）',
  event_hour    TINYINT     NOT NULL                COMMENT '行为小时（冗余，加速活跃时间分析）',
  device_type   VARCHAR(32) NOT NULL                COMMENT '设备：mobile/pc/tablet',
  channel       VARCHAR(32) NOT NULL                COMMENT '渠道：organic/search/ads/campaign/recommendation',
  PRIMARY KEY (id),
  UNIQUE KEY uk_behaviors_behavior_id (behavior_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户行为表';

-- 5. 订单表 orders（开发文档第 10 节）
CREATE TABLE IF NOT EXISTS orders (
  id             BIGINT        NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  order_id       VARCHAR(64)   NOT NULL                COMMENT '订单ID',
  user_id        VARCHAR(32)   NOT NULL                COMMENT '用户ID',
  order_time     DATETIME      NOT NULL                COMMENT '下单时间',
  total_amount   DECIMAL(12,2) NOT NULL DEFAULT 0.00   COMMENT '订单总金额',
  status         VARCHAR(32)   NOT NULL                COMMENT '状态：paid/cancelled/refunded',
  payment_method VARCHAR(32)   NULL                    COMMENT '支付方式',
  PRIMARY KEY (id),
  UNIQUE KEY uk_orders_order_id (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单表';

-- 6. 订单明细表 order_items（开发文档第 11 节）
CREATE TABLE IF NOT EXISTS order_items (
  id         BIGINT        NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  order_id   VARCHAR(64)   NOT NULL                COMMENT '订单ID',
  item_id    VARCHAR(32)   NOT NULL                COMMENT '商品ID',
  quantity   INT           NOT NULL                COMMENT '数量（>0）',
  unit_price DECIMAL(10,2) NOT NULL                COMMENT '成交单价',
  amount     DECIMAL(12,2) NOT NULL                COMMENT '行金额 = quantity * unit_price',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单明细表';

-- ---------------------------------------------------------------------
-- 二、扩展表（开发文档第 5 节"建议增加"，画像/分群/推荐/预测落库）
-- ---------------------------------------------------------------------

-- 7. 用户画像表 user_profile（开发文档第 23.1 节）
CREATE TABLE IF NOT EXISTS user_profile (
  id               BIGINT        NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  user_id          VARCHAR(32)   NOT NULL                COMMENT '用户ID',
  age              INT           NULL                    COMMENT '年龄（快照）',
  gender           VARCHAR(16)   NULL                    COMMENT '性别（快照）',
  city             VARCHAR(64)   NULL                    COMMENT '城市（快照）',
  total_pv         INT           NOT NULL DEFAULT 0      COMMENT '累计浏览',
  total_click      INT           NOT NULL DEFAULT 0      COMMENT '累计点击',
  total_collect    INT           NOT NULL DEFAULT 0      COMMENT '累计收藏',
  total_cart       INT           NOT NULL DEFAULT 0      COMMENT '累计加购',
  total_buy        INT           NOT NULL DEFAULT 0      COMMENT '累计购买',
  total_amount     DECIMAL(12,2) NOT NULL DEFAULT 0.00   COMMENT '累计消费金额',
  avg_order_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00   COMMENT '平均客单价',
  recency          INT           NOT NULL DEFAULT 0      COMMENT '最近活跃距分析日天数',
  frequency        INT           NOT NULL DEFAULT 0      COMMENT '分析周期购买次数',
  monetary         DECIMAL(12,2) NOT NULL DEFAULT 0.00   COMMENT '分析周期消费金额',
  active_days      INT           NOT NULL DEFAULT 0      COMMENT '活跃天数',
  favorite_category VARCHAR(32)  NULL                    COMMENT '偏好分类',
  favorite_brand   VARCHAR(128)  NULL                    COMMENT '偏好品牌',
  preferred_channel VARCHAR(32)  NULL                    COMMENT '偏好渠道',
  preferred_device VARCHAR(32)   NULL                    COMMENT '偏好设备',
  r_score          INT           NULL                    COMMENT 'RFM-最近购买评分1~5',
  f_score          INT           NULL                    COMMENT 'RFM-频次评分1~5',
  m_score          INT           NULL                    COMMENT 'RFM-金额评分1~5',
  rfm_score        INT           NULL                    COMMENT 'RFM综合分',
  rfm_segment      VARCHAR(32)   NULL                    COMMENT 'RFM分群',
  lifecycle_stage  VARCHAR(32)   NULL                    COMMENT '用户生命周期阶段',
  cluster_id       INT           NULL                    COMMENT 'KMeans聚类ID',
  cluster_name     VARCHAR(32)   NULL                    COMMENT '聚类业务命名',
  profile_date     DATE          NOT NULL                COMMENT '画像快照日期',
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_profile_user_date (user_id, profile_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户画像表';

-- 8. 商品画像表 item_profile
CREATE TABLE IF NOT EXISTS item_profile (
  id              BIGINT        NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  item_id         VARCHAR(32)   NOT NULL                COMMENT '商品ID',
  item_name       VARCHAR(255)  NULL                    COMMENT '商品名称（快照）',
  category_id     VARCHAR(32)   NULL                    COMMENT '分类（快照）',
  brand           VARCHAR(128)  NULL                    COMMENT '品牌（快照）',
  price           DECIMAL(10,2) NULL                    COMMENT '价格（快照）',
  pv              INT           NOT NULL DEFAULT 0      COMMENT '曝光/浏览',
  click           INT           NOT NULL DEFAULT 0      COMMENT '点击',
  collect         INT           NOT NULL DEFAULT 0      COMMENT '收藏',
  cart            INT           NOT NULL DEFAULT 0      COMMENT '加购',
  buy             INT           NOT NULL DEFAULT 0      COMMENT '购买',
  gmv             DECIMAL(12,2) NOT NULL DEFAULT 0.00   COMMENT '销售额',
  unique_users    INT           NOT NULL DEFAULT 0      COMMENT '去重购买用户数',
  conversion_rate DECIMAL(10,6) NOT NULL DEFAULT 0      COMMENT '转化率 = buy/pv',
  popularity_score DECIMAL(10,6) NOT NULL DEFAULT 0     COMMENT '综合热门度评分',
  life_stage      VARCHAR(32)   NULL                    COMMENT '商品生命周期阶段',
  profile_date    DATE          NOT NULL                COMMENT '画像快照日期',
  updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_item_profile_date (item_id, profile_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品画像表';

-- 9. 用户分群表 user_segments（RFM / 生命周期 / KMeans 分群结果）
CREATE TABLE IF NOT EXISTS user_segments (
  id           BIGINT      NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  user_id      VARCHAR(32) NOT NULL                COMMENT '用户ID',
  segment_type VARCHAR(32) NOT NULL                COMMENT '分群类型：rfm/lifecycle/kmeans',
  segment_name VARCHAR(32) NOT NULL                COMMENT '分群名称（业务解释）',
  segment_value VARCHAR(64) NULL                   COMMENT '分群明细值（如RFM评分组合）',
  computed_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '计算时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_segments_user_type (user_id, segment_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户分群表';

-- 10. 推荐结果表 recommendation_results
CREATE TABLE IF NOT EXISTS recommendation_results (
  id         BIGINT        NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  user_id    VARCHAR(32)   NOT NULL                COMMENT '用户ID',
  strategy   VARCHAR(32)   NOT NULL                COMMENT '推荐策略：popular/item_cf/user_cf/content/hybrid',
  item_id    VARCHAR(32)   NOT NULL                COMMENT '推荐商品ID',
  score      DECIMAL(10,6) NOT NULL DEFAULT 0      COMMENT '推荐分数',
  rank       INT           NOT NULL                COMMENT '排名（1=最推荐）',
  reason     VARCHAR(255)  NULL                    COMMENT '推荐解释',
  created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='推荐结果表';

-- 11. 模型预测结果表 model_predictions
CREATE TABLE IF NOT EXISTS model_predictions (
  id              BIGINT        NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  user_id         VARCHAR(32)   NOT NULL                COMMENT '用户ID',
  task            VARCHAR(32)   NOT NULL                COMMENT '任务：purchase/churn/value/ctr',
  probability     DECIMAL(8,6)  NULL                    COMMENT '概率类输出（购买/流失/点击概率）',
  predicted_value DECIMAL(12,2) NULL                    COMMENT '数值类输出（如未来30天消费金额）',
  risk_level      VARCHAR(16)   NULL                    COMMENT '风险等级：low/medium/high（流失预测）',
  model_version   VARCHAR(32)   NOT NULL                COMMENT '模型版本（如 v1）',
  predict_date    DATE          NOT NULL                COMMENT '预测日期',
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型预测结果表';

-- 12. 模型指标表 model_metrics
CREATE TABLE IF NOT EXISTS model_metrics (
  id            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  model_name    VARCHAR(64)  NOT NULL                COMMENT '模型名（purchase_prediction/churn_prediction 等）',
  task          VARCHAR(32)  NOT NULL                COMMENT '任务类型',
  version       VARCHAR(32)  NOT NULL                COMMENT '模型版本',
  metrics       JSON         NULL                    COMMENT '评估指标（accuracy/precision/recall/f1/auc 等）',
  feature_count INT          NOT NULL DEFAULT 0      COMMENT '特征数量',
  train_time    DATETIME     NULL                    COMMENT '训练时间',
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_metrics_name_version (model_name, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型指标表';

-- =====================================================================
-- 建表完成。下一步执行: mysql -u root -p < sql/indexes.sql
-- =====================================================================