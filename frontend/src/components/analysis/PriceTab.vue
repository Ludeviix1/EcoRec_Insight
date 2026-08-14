<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtMoney, fmtPct, priceBandLabel } from '@/utils/format'
import type { PriceResponse } from '@/types'

const loading = ref(false)
const data = ref<PriceResponse | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.price()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const bins = computed(() => data.value?.price_bins ?? [])

const option = computed<EChartsOption>(() => {
  const rows = bins.value
  return {
    color: ['#3457a8', '#d98a2b'],
    tooltip: { ...baseTooltip('item'), formatter: (p: any) => `${p.name}<br/>${p.seriesName}: ${p.seriesName === '购买率' ? fmtPct(p.value) : fmtMoney(p.value)}` },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: '#6b7280', fontSize: 12 } },
    grid: { left: 56, right: 20, top: 32, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => priceBandLabel(r.bin_label)), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 10, interval: 0, rotate: 18 } },
    yAxis: [
      { type: 'value', name: '销售额', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
      { type: 'value', name: '购买率', min: 0, max: 0.15, splitLine: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 11, formatter: (v: number) => fmtPct(v, 0) } },
    ],
    series: [
      { name: '销售额', type: 'bar', data: rows.map((r) => r.gmv), itemStyle: { color: '#3457a8', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 30 },
      { name: '购买率', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: true, data: rows.map((r) => r.buy_rate), lineStyle: { color: '#d98a2b', width: 2 } },
    ],
  }
})
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="section-title">价格带：销售额与购买率</div>
      <EChart :option="option" height="300px" />
    </div>
    <div class="card card-pad">
      <div class="section-title">价格带明细</div>
      <el-table :data="bins" size="small" class="dense-table" stripe>
        <el-table-column prop="bin_label" label="价格带" min-width="150">
          <template #default="{ row }">{{ priceBandLabel(row.bin_label) }}</template>
        </el-table-column>
        <el-table-column label="商品数" width="90" align="right"><template #default="{ row }">{{ fmtInt(row.item_count) }}</template></el-table-column>
        <el-table-column label="浏览" width="90" align="right"><template #default="{ row }">{{ fmtInt(row.pv) }}</template></el-table-column>
        <el-table-column label="购买率" width="90" align="right"><template #default="{ row }">{{ fmtPct(row.buy_rate) }}</template></el-table-column>
        <el-table-column label="订单数" width="90" align="right"><template #default="{ row }">{{ fmtInt(row.orders) }}</template></el-table-column>
        <el-table-column label="销售额" width="130" align="right"><template #default="{ row }">{{ fmtMoney(row.gmv) }}</template></el-table-column>
        <el-table-column label="人均频次" width="100" align="right"><template #default="{ row }">{{ row.buy_freq?.toFixed(2) ?? '-' }}</template></el-table-column>
      </el-table>
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">{{ data?.definition }}</div>
    </div>
  </div>
</template>
