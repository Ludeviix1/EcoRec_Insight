/** 全局 API 类型定义：与 backend 响应结构保持一致。 */

export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

export interface Page<T> {
  total: number
  limit: number
  offset: number
  items: T[]
}

/* ---------------- Dashboard ---------------- */

export interface Overview {
  total_users: number | null
  new_users: number | null
  active_users: number | null
  buying_users: number | null
  pay_rate: number | null
  gmv_total: number | null
  order_count: number | null
  aov: number | null
  arpu: number | null
  dau_latest: number | null
  wau_latest: number | null
  mau_latest: number | null
}

export interface TrendPoint {
  date: string
  value: number
}

export interface UserTrend {
  dau: TrendPoint[]
  wau: TrendPoint[]
  mau: TrendPoint[]
  register_trend: { date: string; count: number }[]
  gender_distribution: { label: string; count: number }[]
  city_distribution: { label: string; count: number }[]
}

export interface GmvPoint {
  date: string
  gmv: number
  orders: number
  buying_users: number
  aov: number
  arpu: number
}

export interface GmvTrend {
  daily_trend: GmvPoint[]
  weekly_trend: GmvPoint[]
  monthly_trend: GmvPoint[]
  status_distribution: Record<string, number>
}

export interface BehaviorTrend {
  total: number
  counts: Record<string, number>
  rates: Record<string, number>
  daily_trend: { date: string; pv: number; click: number; collect: number; cart: number; buy: number }[]
  by_hour: { hour: number; pv: number; buy: number; total: number }[]
  by_weekday: { weekday: number; count: number }[]
  by_device_hour: { device: string; hours: number[] }[]
}

export interface FunnelStage {
  stage: string
  count: number
  step_conversion_rate: number
  overall_conversion_rate: number
}

export interface Funnel {
  definition?: string
  stages: string[]
  steps: FunnelStage[]
}

export interface CohortRow {
  cohort_date: string
  size: number
  rate_day_0: number
  rate_day_1: number
  rate_day_3: number
  rate_day_7: number
  rate_day_14: number
  rate_day_30: number
}

export interface Retention {
  definition: string
  offsets: number[]
  overall: { offset: number; label: string; rate: number; base: number; retained: number }[]
  cohort_base: string
  cohort_offsets: number[]
  cohorts: CohortRow[]
}

/* ---------------- Users ---------------- */

export interface UserRow {
  user_id: string
  age: number
  gender: string
  city: string
  register_time: string
}

export interface UserSummary {
  behavior: { pv: number; click: number; collect: number; cart: number; buy: number; active_days: number } | null
  purchase: { order_count: number; gmv: number; aov: number } | null
  spending_power: string | null
  lifecycle_stage: string | null
  rfm: { segment: string; rfm_score: number } | null
}

export interface UserDetail extends UserRow {
  summary: UserSummary
}

export interface UserProfile {
  user_id: string
  basic: { age: number; gender: string; city: string; register_days: number }
  behavior: { pv: number; click: number; collect: number; cart: number; buy: number; active_days: number }
  purchase: { order_count: number; gmv: number; aov: number }
  spending_power: string | null
  active_time: { peak_hour: number; peak_weekday: number }
  preferred_categories: { value: string; count: number }[]
  preferred_brands: { value: string; count: number }[]
  lifecycle_stage: string | null
  rfm: { segment: string; rfm_score: number } | null
  channel: string | null
  device: string | null
  predictions: {
    purchase: { user_id: string; purchase_probability: number; obs_end: string; label_days: number; model: string } | null
    churn: { user_id: string; churn_probability: number; risk_level: string; obs_end: string } | null
  }
}

export interface UserBehavior {
  event_time: string
  event_date: string
  event_hour: number
  behavior_type: string
  item_id: string
  device_type: string
  channel: string
}

export interface OrderItem {
  order_id: string
  item_id: string
  quantity: number
  unit_price: number
  amount: number
  item_name?: string
}

export interface Order {
  order_id: string
  order_time: string
  total_amount: number
  status: string
  payment_method: string
  order_items: OrderItem[]
}

/* ---------------- Items ---------------- */

export interface ItemRow {
  item_id: string
  item_name: string
  category_id: string
  category_name?: string
  brand: string
  price: number
  stock: number
  status: number
  created_at: string
}

export interface ItemStatistics {
  behavior: { pv: number; click: number; collect: number; cart: number; buy: number; unique_users: number; conversion_rate: number } | null
  sales: { sold: number; orders: number; gmv: number } | null
  lifecycle_stage: string | null
  price_band: string | null
  heat_score: number | null
}

export interface RankingItem {
  item_id: string
  item_name: string
  category_id: string
  brand: string
  price: number
  status: number
  pv: number
  click: number
  collect: number
  cart: number
  buy: number
  gmv: number
  unique_users: number
  conversion_rate: number
  heat_score: number
}

export interface RankingCategory {
  category_id: string
  category_name?: string
  users: number
  pv: number
  click: number
  collect: number
  cart: number
  buy: number
  orders: number
  gmv: number
  conversion_rate: number
}

export interface RankingBrand {
  brand: string
  gmv: number
  sold: number
  buy_users: number
  orders: number
  users: number
  aov: number
}

export interface Rankings {
  top_n: number
  items: RankingItem[]
  categories: RankingCategory[]
  brands: RankingBrand[]
}

/* ---------------- 深度分析 ---------------- */

export interface RfmSegment {
  segment: string
  count: number
  gmv: number
  ratio: number
}

export interface LifecycleStage {
  stage: string
  count: number
  ratio: number
  gmv: number
  avg_amount: number
}

export interface SegmentCluster {
  cluster_id: number
  cluster_name: string
  size: number
  ratio: number
  feature_means: Record<string, number>
  interpretation: string
}

export interface ChannelRow {
  channel: string
  users: number
  new_users: number
  new_user_ratio: number
  active_ratio: number
  pv: number
  click: number
  collect: number
  cart: number
  buy: number
  click_rate: number
  buy_rate: number
  orders: number
  gmv: number
  aov: number
}

export interface DeviceRow {
  device: string
  users: number
  behavior_ratio: number
  pv: number
  click: number
  collect: number
  cart: number
  buy: number
  click_rate: number
  buy_rate: number
  orders: number
  gmv: number
  aov: number
  evening_ratio: number
  peak_hour: number
}

export interface PriceBin {
  bin_label: string
  price_min: number
  price_max: number
  item_count: number
  pv: number
  click: number
  cart: number
  buy: number
  click_rate: number
  cart_rate: number
  buy_rate: number
  orders: number
  gmv: number
  buy_users: number
  buy_freq: number
}

export interface AssociationRule {
  antecedents: string | string[]
  consequents: string | string[]
  support: number
  confidence: number
  lift: number
  count: number
}

export interface PathRow {
  path: string
  sessions: number
  users: number
  buy_sessions: number
  final_buy_rate: number
}

export interface Finding {
  metric?: string
  '现象': string
  '证据': string[]
  '可能原因': string
  '业务建议': string
}

export interface FindingDomain {
  domain: string
  title: string
  findings: Finding[]
}

/* ---------------- 预测模型 ---------------- */

export interface ModelMetrics {
  [model: string]: {
    test: {
      n_samples: number
      positive_rate: number
      accuracy: number
      precision: number
      recall: number
      f1: number
      roc_auc: number
      pr_auc: number
      confusion_matrix: number[][]
    }
  }
}

export interface ModelDetail {
  task: string
  description: string
  time_windows: Record<string, unknown>
  leakage_guard: string
  data_split: Record<string, unknown>
  config?: Record<string, unknown>
  run_at: string
  metrics: ModelMetrics
  best_model: { model: string; selection: string; test: Record<string, unknown> } | null
  feature_importance: { feature: string; importance?: number; coef?: number; abs_coef?: number }[]
  predictions?: ChurnPrediction[]
  risk_level?: Record<string, number>
}

export interface ChurnPrediction {
  user_id: string
  churn_probability: number
  risk_level: string
  obs_end: string
}

/* ---------------- 推荐 ---------------- */

export interface RecItem {
  item_id: string
  item_name: string
  category_id: string
  brand: string
  price: number
  score: number
  reason: string
}

export interface RecResult {
  user_id: string
  algorithm: string
  top_k: number
  count: number
  items: RecItem[]
  error?: string
}

export interface RecCompare {
  user_id: string
  top_k: number
  algorithms: string[]
  results: Record<string, RecResult>
}

export interface EvalRow {
  algorithm: string
  'precision@k': number
  'recall@k': number
  'f1@k': number
  'hit_rate@k': number
  'ndcg@k': number
  'coverage@k': number
}

export interface RecMetrics {
  method: string
  k: number
  test_ratio: number
  max_users: number
  baseline: string
  conclusion: string
  algorithms: EvalRow[]
  weight_experiment: {
    best_experiment: string
    best_weights: Record<string, number>
    selection_criterion: string
    note?: string
    variants?: { experiment: string; weights: Record<string, number> }[]
  }
}

export interface ModelsMetrics {
  purchase: Record<string, ModelTestScore>
  churn: Record<string, ModelTestScore>
  recommendation: {
    k: number
    test_ratio: number
    baseline: string
    conclusion: string
    algorithms: EvalRow[]
  }
  weight_experiment: {
    best_experiment: string
    best_weights: Record<string, number>
    selection_criterion: string
    variants: { experiment: string; weights: Record<string, number> }[]
  }
}

export interface ModelTestScore {
  n_samples: number
  positive_rate: number
  accuracy: number
  precision: number
  recall: number
  f1: number
  roc_auc: number
  pr_auc: number
  confusion_matrix: number[][]
}

/* ---------------- 分析端点响应包装 ---------------- */
/* 分析接口返回包装对象（含定义/配置 + 明细列表），非裸数组。 */

export interface RfmResponse {
  definition?: Record<string, unknown>
  scoring?: Record<string, unknown>
  total_buying_users?: number
  segment_distribution: RfmSegment[]
  score_distribution?: Record<string, unknown>
  users?: Record<string, unknown>[]
}

export interface LifecycleResponse {
  definition?: string
  config?: Record<string, unknown>
  total_users?: number
  distribution: LifecycleStage[]
  users?: Record<string, unknown>[]
}

export interface SegmentsResponse {
  definition?: string
  features?: string[]
  n_clusters?: number
  random_state?: number
  clusters: SegmentCluster[]
  users?: Record<string, unknown>[]
}

export interface ChannelResponse {
  definition?: string
  note?: string
  config?: Record<string, unknown>
  as_of_date?: string
  channels: ChannelRow[]
}

export interface DeviceResponse {
  definition?: string
  config?: Record<string, unknown>
  devices: DeviceRow[]
}

export interface PriceResponse {
  definition?: string
  config?: Record<string, unknown>
  total_price_bins?: number
  price_bins: PriceBin[]
  cross?: Record<string, unknown>
}

export interface AssociationResponse {
  definition?: string
  config?: Record<string, unknown>
  total_orders?: number
  item_rules_count?: number
  category_rules_count?: number
  item_rules: AssociationRule[]
  category_rules: AssociationRule[]
}

export interface PathResponse {
  definition?: string
  config?: Record<string, unknown>
  total_sessions?: number
  total_users?: number
  distinct_paths?: number
  top_paths: PathRow[]
  longest_path?: Record<string, unknown>
}

export interface FindingsResponse {
  disclaimer?: string
  total_domains?: number
  domains: FindingDomain[]
}

export interface UserBehaviorPage {
  user_id: string
  total: number
  limit: number
  items: UserBehavior[]
}

export interface OrderPage {
  user_id: string
  total?: number
  items: Order[]
}
