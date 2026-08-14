<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { PALETTE, baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtMoney, fmtPct, channelLabel } from '@/utils/format'
import type { ChannelResponse } from '@/types'

const loading = ref(false)
const data = ref<ChannelResponse | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.channel()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const channels = computed(() => data.value?.channels ?? [])

const option = computed<EChartsOption>(() => {
  const rows = channels.value
  return {
    color: PALETTE,
    tooltip: baseTooltip('axis'),
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: '#6b7280', fontSize: 12 } },
    grid: { left: 48, right: 20, top: 32, bottom: 30, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => channelLabel(r.channel)), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      { name: '浏览', type: 'bar', data: rows.map((r) => r.pv), itemStyle: { color: '#6ba3d0', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 24 },
      { name: '购买', type: 'bar', data: rows.map((r) => r.buy), itemStyle: { color: '#c0504d', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 24 },
    ],
  }
})
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="section-title">各渠道浏览 / 购买对比</div>
      <EChart :option="option" height="280px" />
    </div>
    <div class="card card-pad">
      <div class="section-title">渠道质量明细</div>
      <el-table :data="channels" size="small" class="dense-table" stripe>
        <el-table-column label="渠道" min-width="100">
          <template #default="{ row }">{{ channelLabel(row.channel) }}</template>
        </el-table-column>
        <el-table-column label="用户数" width="100" align="right"><template #default="{ row }">{{ fmtInt(row.users) }}</template></el-table-column>
        <el-table-column label="新用户" width="90" align="right"><template #default="{ row }">{{ fmtInt(row.new_users) }}</template></el-table-column>
        <el-table-column label="点击率" width="100" align="right"><template #default="{ row }">{{ fmtPct(row.click_rate) }}</template></el-table-column>
        <el-table-column label="购买率" width="100" align="right"><template #default="{ row }">{{ fmtPct(row.buy_rate) }}</template></el-table-column>
        <el-table-column label="订单数" width="100" align="right"><template #default="{ row }">{{ fmtInt(row.orders) }}</template></el-table-column>
        <el-table-column label="销售额" width="130" align="right"><template #default="{ row }">{{ fmtMoney(row.gmv) }}</template></el-table-column>
        <el-table-column label="客单价" width="110" align="right"><template #default="{ row }">{{ fmtMoney(row.aov) }}</template></el-table-column>
      </el-table>
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">
        {{ data?.definition }}<br v-if="data?.note" />{{ data?.note }}
      </div>
    </div>
  </div>
</template>
