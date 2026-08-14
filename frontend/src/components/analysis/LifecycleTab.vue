<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { PALETTE, baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtMoney, fmtPct } from '@/utils/format'
import { stageTagType } from '@/utils/format'
import type { LifecycleResponse } from '@/types'

const loading = ref(false)
const data = ref<LifecycleResponse | null>(null)
const metric = ref<'count' | 'gmv'>('count')

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.lifecycle()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const distribution = computed(() => data.value?.distribution ?? [])

const option = computed<EChartsOption>(() => {
  const rows = distribution.value
  return {
    color: PALETTE,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: 'rgba(30,41,59,0.92)',
      borderWidth: 0,
      textStyle: { color: '#f1f5f9', fontSize: 12 },
      formatter: (ps: any) => `${ps[0].name}<br/>${metric.value === 'count' ? '人数' : '销售额'}: ${metric.value === 'count' ? fmtInt(ps[0].value) : fmtMoney(ps[0].value)}`,
    },
    grid: { left: 48, right: 20, top: 16, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.stage), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11, interval: 0, rotate: 18 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      {
        type: 'bar',
        data: rows.map((r, i) => ({ value: metric.value === 'count' ? r.count : r.gmv, itemStyle: { color: PALETTE[i % PALETTE.length], borderRadius: [4, 4, 0, 0] } })),
        barMaxWidth: 48,
        label: { show: true, position: 'top', color: '#6b7280', fontSize: 11, formatter: (p: any) => metric.value === 'count' ? fmtInt(p.value) : fmtMoney(p.value) },
      },
    ],
  }
})
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="flex-between">
        <div class="section-title">生命周期分布</div>
        <el-radio-group v-model="metric" size="small">
          <el-radio-button value="count">按人数</el-radio-button>
          <el-radio-button value="gmv">按销售额</el-radio-button>
        </el-radio-group>
      </div>
      <EChart :option="option" height="300px" />
    </div>
    <div class="card card-pad">
      <div class="section-title">阶段明细</div>
      <el-table :data="distribution" size="small" class="dense-table" stripe>
        <el-table-column label="生命周期阶段" min-width="140">
          <template #default="{ row }">
            <el-tag :type="stageTagType(row.stage) as any" size="small" effect="light">{{ row.stage }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="人数" width="100" align="right"><template #default="{ row }">{{ fmtInt(row.count) }}</template></el-table-column>
        <el-table-column label="占比" width="100" align="right"><template #default="{ row }">{{ fmtPct(row.ratio) }}</template></el-table-column>
        <el-table-column label="销售额" width="140" align="right"><template #default="{ row }">{{ fmtMoney(row.gmv) }}</template></el-table-column>
        <el-table-column label="人均消费" width="140" align="right"><template #default="{ row }">{{ fmtMoney(row.avg_amount) }}</template></el-table-column>
      </el-table>
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">{{ data?.definition }}</div>
    </div>
  </div>
</template>
