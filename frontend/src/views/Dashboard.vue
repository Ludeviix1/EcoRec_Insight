<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import ChartCard from '@/components/ChartCard.vue'
import StatCard from '@/components/StatCard.vue'
import PageHeader from '@/components/PageHeader.vue'
import { dashboardApi } from '@/api'
import { PALETTE, BEHAVIOR_COLORS, baseGrid, baseTooltip, baseLegend, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtMoney, fmtMoneyFull, fmtPct, fmtNum, behaviorLabel } from '@/utils/format'
import type { Overview, UserTrend, GmvTrend, BehaviorTrend, Funnel, Retention, Rankings } from '@/types'

const loading = ref(true)
const overview = ref<Overview | null>(null)
const userTrend = ref<UserTrend | null>(null)
const gmvTrend = ref<GmvTrend | null>(null)
const behavior = ref<BehaviorTrend | null>(null)
const funnel = ref<Funnel | null>(null)
const retention = ref<Retention | null>(null)
const rankings = ref<Rankings | null>(null)
const gmvGranularity = ref<'daily_trend' | 'weekly_trend' | 'monthly_trend'>('daily_trend')

async function loadAll() {
  loading.value = true
  const [ov, ut, gt, bt, fn, rt, rk] = await Promise.allSettled([
    dashboardApi.overview(),
    dashboardApi.userTrend(),
    dashboardApi.gmvTrend(),
    dashboardApi.behaviorTrend(),
    dashboardApi.funnel(),
    dashboardApi.retention(),
    dashboardApi.rankings(10),
  ])
  if (ov.status === 'fulfilled') overview.value = ov.value
  if (ut.status === 'fulfilled') userTrend.value = ut.value
  if (gt.status === 'fulfilled') gmvTrend.value = gt.value
  if (bt.status === 'fulfilled') behavior.value = bt.value
  if (fn.status === 'fulfilled') funnel.value = fn.value
  if (rt.status === 'fulfilled') retention.value = rt.value
  if (rk.status === 'fulfilled') rankings.value = rk.value
  loading.value = false
}
onMounted(loadAll)

/* ---------- KPI ---------- */
const kpis = computed(() => {
  const o = overview.value
  return [
    { label: '总用户数', value: fmtInt(o?.total_users), icon: 'User', accent: '#3457a8' },
    { label: '活跃用户', value: fmtInt(o?.active_users), icon: 'Aim', accent: '#4a9d9c' },
    { label: '购买用户', value: fmtInt(o?.buying_users), icon: 'ShoppingCart', accent: '#c0504d' },
    { label: '支付率', value: fmtPct(o?.pay_rate), icon: 'TrendCharts', accent: '#d98a2b' },
    { label: '累计销售额', value: fmtMoney(o?.gmv_total), hint: fmtMoneyFull(o?.gmv_total), icon: 'Money', accent: '#2f9e6e' },
    { label: '订单数', value: fmtInt(o?.order_count), icon: 'Document', accent: '#8e6fc0' },
    { label: '客单价', value: fmtMoney(o?.aov), icon: 'Coin', accent: '#3a8fb7' },
    { label: '人均收入', value: fmtMoney(o?.arpu), icon: 'PieChart', accent: '#c9a13a' },
    { label: '日活跃用户', value: fmtInt(o?.dau_latest), icon: 'DataLine', accent: '#5a8f4b' },
    { label: '月活跃用户', value: fmtInt(o?.mau_latest), icon: 'Histogram', accent: '#b07a9e' },
  ]
})

/* ---------- DAU/WAU/MAU 趋势 ---------- */
const dauOption = computed<EChartsOption>(() => {
  const d = userTrend.value
  const dau = d?.dau ?? []
  const wau = d?.wau ?? []
  const mau = d?.mau ?? []
  return {
    color: PALETTE,
    tooltip: baseTooltip(),
    legend: baseLegend(),
    grid: baseGrid(),
    xAxis: { type: 'category', data: dau.map((p) => p.date.slice(5)), boundaryGap: false, axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      { name: '日活跃', type: 'line', smooth: true, showSymbol: false, data: dau.map((p) => p.value), lineStyle: { width: 2 }, areaStyle: { opacity: 0.12 } },
      { name: '周活跃', type: 'line', smooth: true, showSymbol: false, data: wau.map((p) => p.value), lineStyle: { width: 2 } },
      { name: '月活跃', type: 'line', smooth: true, showSymbol: false, data: mau.map((p) => p.value), lineStyle: { width: 2 } },
    ],
  }
})

/* ---------- 行为分布 ---------- */
const behaviorPieOption = computed<EChartsOption>(() => {
  const counts = behavior.value?.counts ?? {}
  const data = ['pv', 'click', 'collect', 'cart', 'buy'].map((k) => ({ name: behaviorLabel(k), value: counts[k] ?? 0, itemStyle: { color: BEHAVIOR_COLORS[k] } }))
  return {
    tooltip: baseTooltip('item'),
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { color: '#6b7280', fontSize: 12 } },
    series: [
      {
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 13, fontWeight: 600 } },
        data,
      },
    ],
  }
})

/* ---------- GMV 趋势 ---------- */
const gmvOption = computed<EChartsOption>(() => {
  const g = gmvTrend.value
  const rows = g?.[gmvGranularity.value] ?? []
  return {
    color: PALETTE,
    tooltip: baseTooltip(),
    legend: { top: 0, right: 0, data: ['销售额', '订单数'], icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: '#6b7280', fontSize: 12 } },
    grid: baseGrid(),
    xAxis: { type: 'category', data: rows.map((p) => p.date.slice(5)), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: [
      { type: 'value', name: '销售额', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
      { type: 'value', name: '订单', splitLine: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    ],
    series: [
      { name: '销售额', type: 'bar', data: rows.map((p) => p.gmv), itemStyle: { color: '#3457a8', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 22 },
      { name: '订单数', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: rows.map((p) => p.orders), lineStyle: { color: '#d98a2b', width: 2 } },
    ],
  }
})

/* ---------- 行为按小时 ---------- */
const byHourOption = computed<EChartsOption>(() => {
  const rows = behavior.value?.by_hour ?? []
  return {
    color: ['#6ba3d0', '#c0504d'],
    tooltip: baseTooltip(),
    legend: baseLegend(),
    grid: baseGrid(),
    xAxis: { type: 'category', data: rows.map((r) => r.hour + '时'), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      { name: '浏览', type: 'bar', data: rows.map((r) => r.pv), itemStyle: { color: '#6ba3d0', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 14 },
      { name: '购买', type: 'line', smooth: true, showSymbol: false, data: rows.map((r) => r.buy), lineStyle: { color: '#c0504d', width: 2 } },
    ],
  }
})

/* ---------- 漏斗 ---------- */
const funnelOption = computed<EChartsOption>(() => {
  const steps = funnel.value?.steps ?? []
  const colors = ['#3457a8', '#4a9d9c', '#d98a2b', '#8e6fc0', '#c0504d']
  return {
    color: colors,
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `${p.name}<br/>数量：${fmtInt(p.value)}<br/>整体转化：${fmtPct(p.data?.overall)}`,
      backgroundColor: 'rgba(30,41,59,0.92)',
      borderWidth: 0,
      textStyle: { color: '#f1f5f9', fontSize: 12 },
    },
    series: [
      {
        type: 'funnel',
        left: '8%',
        right: '8%',
        top: 10,
        bottom: 10,
        minSize: '28%',
        sort: 'descending',
        gap: 2,
        label: { show: true, position: 'inside', color: '#fff', fontSize: 12, fontWeight: 600 },
        itemStyle: { borderColor: '#fff', borderWidth: 1 },
        data: steps.map((s, i) => ({ name: behaviorLabel(s.stage), value: s.count, overall: s.overall_conversion_rate, itemStyle: { color: colors[i] } })),
      },
    ],
  }
})

/* ---------- Cohort 热力图 ---------- */
const cohortOption = computed<EChartsOption>(() => {
  const cohorts = retention.value?.cohorts ?? []
  const offsets = retention.value?.cohort_offsets ?? [1, 3, 7, 14, 30]
  const labels = ['当日', ...offsets.map((o) => '+' + o + '天')]
  // 取最近 14 个 cohort 展示
  const rows = cohorts.slice(-14)
  const data: [number, number, number][] = []
  let max = 0
  rows.forEach((c, y) => {
    const vals = [c.rate_day_0 ?? 0, c.rate_day_1 ?? 0, c.rate_day_3 ?? 0, c.rate_day_7 ?? 0, c.rate_day_14 ?? 0, c.rate_day_30 ?? 0]
    vals.forEach((v, x) => {
      if (v > max) max = v
      data.push([x, rows.length - 1 - y, v])
    })
  })
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `同期群: ${rows[rows.length - 1 - p.value[1]]?.cohort_date?.slice(0, 10)}<br/>${labels[p.value[0]]}: ${fmtPct(p.value[2])}`,
      backgroundColor: 'rgba(30,41,59,0.92)',
      borderWidth: 0,
      textStyle: { color: '#f1f5f9', fontSize: 12 },
    },
    grid: { left: 90, right: 16, top: 16, bottom: 28, containLabel: false },
    xAxis: { type: 'category', data: labels, splitArea: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 11 }, axisLine: { lineStyle: { color: '#d1d5db' } } },
    yAxis: { type: 'category', data: rows.map((r) => r.cohort_date.slice(0, 10)).reverse(), axisLabel: { color: '#9ca3af', fontSize: 10 }, axisLine: { lineStyle: { color: '#d1d5db' } } },
    visualMap: {
      min: 0,
      max: max || 1,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      show: false,
      inRange: { color: ['#eef2f9', '#9fb6db', '#3457a8'] },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: { show: true, color: '#374151', fontSize: 10, formatter: (p: any) => fmtPct(p.value[2], 0) },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.2)' } },
      },
    ],
  }
})

/* ---------- 排行 ---------- */
const topItems = computed(() => rankings.value?.items ?? [])
const categoryOption = computed<EChartsOption>(() => {
  const cats = (rankings.value?.categories ?? []).slice(0, 8)
  return {
    color: PALETTE,
    tooltip: baseTooltip('item'),
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'category', data: cats.map((c) => c.category_id).reverse(), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [{ type: 'bar', data: cats.map((c) => c.gmv).reverse(), itemStyle: { color: '#4a9d9c', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 16 }],
  }
})
const brandOption = computed<EChartsOption>(() => {
  const brands = (rankings.value?.brands ?? []).slice(0, 8)
  return {
    color: PALETTE,
    tooltip: baseTooltip('item'),
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'category', data: brands.map((b) => b.brand).reverse(), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [{ type: 'bar', data: brands.map((b) => b.gmv).reverse(), itemStyle: { color: '#d98a2b', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 16 }],
  }
})
</script>

<template>
  <div>
    <PageHeader title="仪表盘" desc="用户规模 · 活跃趋势 · 销售额 · 行为 · 转化漏斗 · 同期群留存 · 商品排行" />

    <!-- KPI -->
    <div class="kpi-grid" v-loading="loading">
      <StatCard
        v-for="k in kpis"
        :key="k.label"
        :label="k.label"
        :value="k.value"
        :hint="(k as any).hint"
        :icon="k.icon"
        :accent="k.accent"
      />
    </div>

    <!-- 趋势区 -->
    <el-row :gutter="16" class="mt-16">
      <el-col :xs="24" :lg="16">
        <ChartCard title="用户活跃趋势" subtitle="日活跃 / 周活跃 / 月活跃" height="320px" :loading="loading">
          <EChart :option="dauOption" height="300px" />
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="8">
        <ChartCard title="行为类型分布" height="320px" :loading="loading">
          <EChart :option="behaviorPieOption" height="300px" />
        </ChartCard>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt-16">
      <el-col :xs="24" :lg="16">
        <ChartCard title="销售额趋势" height="320px" :loading="loading">
          <template #head>
            <el-radio-group v-model="gmvGranularity" size="small">
              <el-radio-button value="daily_trend">日</el-radio-button>
              <el-radio-button value="weekly_trend">周</el-radio-button>
              <el-radio-button value="monthly_trend">月</el-radio-button>
            </el-radio-group>
          </template>
          <EChart :option="gmvOption" height="300px" />
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="8">
        <ChartCard title="转化漏斗" subtitle="浏览 → 点击 → 收藏 → 加购 → 购买" height="320px" :loading="loading">
          <EChart :option="funnelOption" height="300px" />
        </ChartCard>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt-16">
      <el-col :xs="24" :lg="12">
        <ChartCard title="活跃时段分布" subtitle="按小时浏览与购买" height="300px" :loading="loading">
          <EChart :option="byHourOption" height="280px" />
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="12">
        <ChartCard title="同期群留存矩阵" subtitle="最近 14 个首次活跃同期群" height="300px" :loading="loading">
          <EChart :option="cohortOption" height="280px" />
        </ChartCard>
      </el-col>
    </el-row>

    <!-- 排行 -->
    <el-row :gutter="16" class="mt-16">
      <el-col :xs="24" :lg="12">
        <ChartCard title="热销商品 Top 10" height="auto">
          <el-table :data="topItems" size="small" class="dense-table" stripe>
            <el-table-column type="index" label="#" width="42" />
            <el-table-column prop="item_name" label="商品" min-width="160" show-overflow-tooltip />
            <el-table-column prop="brand" label="品牌" width="90" show-overflow-tooltip />
            <el-table-column label="销售额" width="110" align="right">
              <template #default="{ row }">{{ fmtMoney(row.gmv) }}</template>
            </el-table-column>
            <el-table-column label="购买" width="80" align="right">
              <template #default="{ row }">{{ fmtInt(row.buy) }}</template>
            </el-table-column>
            <el-table-column label="转化率" width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.conversion_rate) }}</template>
            </el-table-column>
          </el-table>
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="6">
        <ChartCard title="分类销售额" height="280px">
          <EChart :option="categoryOption" height="260px" />
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="6">
        <ChartCard title="品牌销售额" height="280px">
          <EChart :option="brandOption" height="260px" />
        </ChartCard>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}
</style>
