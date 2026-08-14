<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { PALETTE, baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtMoney, fmtPct, deviceLabel } from '@/utils/format'
import type { DeviceResponse } from '@/types'

const loading = ref(false)
const data = ref<DeviceResponse | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.device()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const devices = computed(() => data.value?.devices ?? [])

const option = computed<EChartsOption>(() => {
  const rows = devices.value
  return {
    color: PALETTE,
    tooltip: { ...baseTooltip('item'), formatter: (p: any) => `${p.name}<br/>浏览: ${fmtInt(p.value)}` },
    grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'category', data: rows.map((r) => deviceLabel(r.device)).reverse(), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#6b7280', fontSize: 11 } },
    series: [{ type: 'bar', data: rows.map((r) => r.pv).reverse(), itemStyle: { color: '#4a9d9c', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 22 }],
  }
})
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="section-title">设备活跃对比</div>
      <EChart :option="option" height="220px" />
    </div>
    <div class="card card-pad">
      <div class="section-title">设备明细</div>
      <el-table :data="devices" size="small" class="dense-table" stripe>
        <el-table-column label="设备" min-width="90">
          <template #default="{ row }">{{ deviceLabel(row.device) }}</template>
        </el-table-column>
        <el-table-column label="用户数" width="100" align="right"><template #default="{ row }">{{ fmtInt(row.users) }}</template></el-table-column>
        <el-table-column label="行为占比" width="110" align="right"><template #default="{ row }">{{ fmtPct(row.behavior_ratio) }}</template></el-table-column>
        <el-table-column label="点击率" width="100" align="right"><template #default="{ row }">{{ fmtPct(row.click_rate) }}</template></el-table-column>
        <el-table-column label="购买率" width="100" align="right"><template #default="{ row }">{{ fmtPct(row.buy_rate) }}</template></el-table-column>
        <el-table-column label="销售额" width="130" align="right"><template #default="{ row }">{{ fmtMoney(row.gmv) }}</template></el-table-column>
        <el-table-column label="晚间占比" width="100" align="right"><template #default="{ row }">{{ fmtPct(row.evening_ratio) }}</template></el-table-column>
        <el-table-column label="高峰时段" width="90" align="right"><template #default="{ row }">{{ row.peak_hour }} 时</template></el-table-column>
      </el-table>
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">{{ data?.definition }}</div>
    </div>
  </div>
</template>
