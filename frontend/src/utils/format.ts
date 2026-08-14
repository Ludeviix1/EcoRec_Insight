/** 数字 / 日期 / 百分比 格式化工具。 */

/** 千分位整数。 */
export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return Math.round(v).toLocaleString('en-US')
}

/** 保留指定小数位的数值（默认 2 位），带千分位。 */
export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** 货币（元）：万 / 亿 简写。 */
export function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  const abs = Math.abs(v)
  if (abs >= 1e8) return (v / 1e8).toFixed(2) + ' 亿'
  if (abs >= 1e4) return (v / 1e4).toFixed(2) + ' 万'
  return fmtNum(v, 2)
}

/** 货币全量（元，千分位 2 位）。 */
export function fmtMoneyFull(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return '¥' + fmtNum(v, 2)
}

/** 百分比：0.1234 -> 12.34%。 */
export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return (Number(v) * 100).toFixed(digits) + '%'
}

/** 0~1 概率展示为百分比。 */
export function fmtProb(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return (Number(v) * 100).toFixed(digits) + '%'
}

/** 日期截断到 YYYY-MM-DD。 */
export function fmtDate(s: string | null | undefined): string {
  if (!s) return '-'
  return String(s).slice(0, 10)
}

/** 日期时间截断到分钟。 */
export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return '-'
  return String(s).slice(0, 16).replace('T', ' ')
}

/** 工作日序号 -> 中文。 */
export function weekdayLabel(w: number): string {
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][w] ?? '-'
}

/** 行为类型中文。 */
export function behaviorLabel(t: string): string {
  const m: Record<string, string> = { pv: '浏览', click: '点击', collect: '收藏', cart: '加购', buy: '购买' }
  return m[t] ?? t
}

/** 性别中文。 */
export function genderLabel(g: string | null | undefined): string {
  const m: Record<string, string> = { M: '男', F: '女', male: '男', female: '女' }
  return m[g ?? ''] ?? g ?? '-'
}

/** 渠道中文。 */
export function channelLabel(c: string | null | undefined): string {
  const m: Record<string, string> = { search: '搜索', recommendation: '推荐位', organic: '自然流量', campaign: '活动推广', ads: '广告投放' }
  return m[c ?? ''] ?? c ?? '-'
}

/** 设备中文。 */
export function deviceLabel(d: string | null | undefined): string {
  const m: Record<string, string> = { mobile: '手机端', pc: '电脑端', tablet: '平板端' }
  return m[d ?? ''] ?? d ?? '-'
}

/** 订单状态中文。 */
export function orderStatusLabel(s: string | null | undefined): string {
  const m: Record<string, string> = { paid: '已支付', cancelled: '已取消', refunded: '已退款', pending: '待支付' }
  return m[s ?? ''] ?? s ?? '-'
}

/** 支付方式中文。 */
export function payMethodLabel(s: string | null | undefined): string {
  const m: Record<string, string> = { card: '银行卡', alipay: '支付宝', wechat: '微信支付', balance: '余额支付' }
  return m[s ?? ''] ?? s ?? '-'
}

/** 模型名称中文。 */
export function modelLabel(s: string | null | undefined): string {
  const m: Record<string, string> = { logistic_regression: '逻辑回归', random_forest: '随机森林' }
  return m[s ?? ''] ?? s ?? '-'
}

/** 风险等级中文。 */
export function riskLabel(s: string | null | undefined): string {
  const m: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return m[s ?? ''] ?? s ?? '-'
}

/** 行为路径转中文（pv→click→buy -> 浏览→点击→购买）。 */
export function pathLabel(p: string | null | undefined): string {
  if (!p) return '-'
  return p
    .split('→')
    .map((seg) => behaviorLabel(seg.trim()))
    .join(' → ')
}

/** 价格带数值区间转中文（(1727.702, 19999.0] -> 1728 ~ 19999 元）。 */
export function priceBandLabel(b: string | null | undefined): string {
  if (!b) return '-'
  const m = b.match(/[\[(]\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*[\])]/)
  if (!m) return b
  const lo = Math.ceil(Number(m[1]))
  const hi = Number(m[2]) > 1e9 ? '∞' : Math.floor(Number(m[2]))
  return `${lo} ~ ${hi} 元`
}

/** 风险等级 -> tag type。 */
export function riskTagType(level: string | null | undefined): string {
  if (!level) return 'info'
  const l = level.toLowerCase()
  if (l.includes('high') || l.includes('高')) return 'danger'
  if (l.includes('medium') || l.includes('中')) return 'warning'
  return 'success'
}

/** 生命周期 / 消费力等 -> tag type。 */
export function stageTagType(stage: string | null | undefined): string {
  if (!stage) return 'info'
  if (stage.includes('高价值') || stage.includes('核心') || stage.includes('忠诚')) return 'success'
  if (stage.includes('流失') || stage.includes('沉睡') || stage.includes('休眠')) return 'danger'
  if (stage.includes('成长') || stage.includes('新客') || stage.includes('活跃')) return 'primary'
  if (stage.includes('一般') || stage.includes('普通')) return 'info'
  return 'warning'
}
