-- =====================================================================
-- 电商用户行为分析与智能推荐平台 - 索引脚本 (Phase 2)
-- 执行方式: mysql -u root -p < sql/indexes.sql
-- 前置条件: 已执行 sql/schema.sql
-- 说明:
--   1. 覆盖开发文档第 46 节要求的索引字段：
--      user_id / item_id / event_time / event_date / behavior_type /
--      category_id / order_id。
--   2. 本脚本不幂等：重复执行会因"索引已存在"报错，可忽略，
--      或先执行对应 DROP INDEX 后再执行。
-- =====================================================================

USE ecommerce_recommendation;

-- ---------------------------------------------------------------------
-- users：按注册时间查询（新增用户趋势）
-- ---------------------------------------------------------------------
CREATE INDEX idx_users_register_time ON users (register_time);

-- ---------------------------------------------------------------------
-- items：按分类 / 品牌 / 价格 / 状态筛选商品
-- ---------------------------------------------------------------------
CREATE INDEX idx_items_category_id ON items (category_id);
CREATE INDEX idx_items_brand       ON items (brand);
CREATE INDEX idx_items_price       ON items (price);
CREATE INDEX idx_items_status      ON items (status);

-- ---------------------------------------------------------------------
-- user_behaviors：查询与统计最频繁的表（百万级，索引收益最大）
--   (user_id, event_time)  用户行为序列 / 用户画像特征构建
--   (item_id, event_time)  商品行为统计 / 商品画像
--   event_date             按日统计 DAU / 行为趋势（覆盖 event_time 前缀）
--   behavior_type          按行为类型统计
--   channel / device_type  渠道 / 设备分析
-- ---------------------------------------------------------------------
CREATE INDEX idx_behavior_user_time ON user_behaviors (user_id, event_time);
CREATE INDEX idx_behavior_item_time ON user_behaviors (item_id, event_time);
CREATE INDEX idx_behavior_event_date ON user_behaviors (event_date);
CREATE INDEX idx_behavior_event_time ON user_behaviors (event_time);
CREATE INDEX idx_behavior_type      ON user_behaviors (behavior_type);
CREATE INDEX idx_behavior_channel   ON user_behaviors (channel);
CREATE INDEX idx_behavior_device    ON user_behaviors (device_type);

-- ---------------------------------------------------------------------
-- orders：按用户 / 时间 / 状态查询订单
-- ---------------------------------------------------------------------
CREATE INDEX idx_orders_user_id  ON orders (user_id);
CREATE INDEX idx_orders_order_time ON orders (order_time);
CREATE INDEX idx_orders_status   ON orders (status);

-- ---------------------------------------------------------------------
-- order_items：按订单查明细 / 按商品聚合（关联规则、销量统计）
-- ---------------------------------------------------------------------
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_item_id  ON order_items (item_id);

-- ---------------------------------------------------------------------
-- 扩展表索引
-- ---------------------------------------------------------------------
CREATE INDEX idx_profile_user_id       ON user_profile (user_id);
CREATE INDEX idx_profile_lifecycle     ON user_profile (lifecycle_stage);

CREATE INDEX idx_item_profile_category ON item_profile (category_id);
CREATE INDEX idx_item_profile_life     ON item_profile (life_stage);

CREATE INDEX idx_segments_type_name    ON user_segments (segment_type, segment_name);

CREATE INDEX idx_reco_user_created     ON recommendation_results (user_id, created_at);
CREATE INDEX idx_reco_strategy         ON recommendation_results (strategy, item_id);

CREATE INDEX idx_predict_user          ON model_predictions (user_id);
CREATE INDEX idx_predict_task_date     ON model_predictions (task, predict_date);

-- =====================================================================
-- 索引创建完成。
-- =====================================================================