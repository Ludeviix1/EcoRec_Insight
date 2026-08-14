/** ECharts 统一入口：调色板 + 常用 option 片段。 */

import * as echarts from 'echarts'

/** 沉稳配色：以主蓝为基，辅以克制的对比色。 */
export const PALETTE = [
  '#3457a8',
  '#4a9d9c',
  '#d98a2b',
  '#8e6fc0',
  '#c0504d',
  '#5a8f4b',
  '#6ba3d0',
  '#c9a13a',
  '#3a8fb7',
  '#b07a9e',
]

/** 行为类型固定配色。 */
export const BEHAVIOR_COLORS: Record<string, string> = {
  pv: '#6ba3d0',
  click: '#4a9d9c',
  collect: '#d98a2b',
  cart: '#8e6fc0',
  buy: '#c0504d',
}

export { echarts }

/** 通用网格（带留白），适配卡片内图表。 */
export function baseGrid() {
  return {
    left: 48,
    right: 20,
    top: 24,
    bottom: 36,
    containLabel: true,
  }
}

/** 通用 tooltip。 */
export function baseTooltip(trigger: 'axis' | 'item' = 'axis') {
  return {
    trigger,
    backgroundColor: 'rgba(30,41,59,0.92)',
    borderWidth: 0,
    textStyle: { color: '#f1f5f9', fontSize: 12 },
    axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(52,87,168,0.08)' } },
  }
}

/** 通用图例。 */
export function baseLegend(top = 0) {
  return {
    top,
    right: 0,
    icon: 'roundRect',
    itemWidth: 12,
    itemHeight: 8,
    textStyle: { color: '#6b7280', fontSize: 12 },
  }
}

export type EChartsOption = echarts.EChartsCoreOption
