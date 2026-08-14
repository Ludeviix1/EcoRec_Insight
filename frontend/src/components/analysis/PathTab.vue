<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtPct, pathLabel } from '@/utils/format'
import type { PathResponse } from '@/types'

const loading = ref(false)
const data = ref<PathResponse | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.path()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const paths = computed(() => data.value?.top_paths ?? [])

const option = computed<EChartsOption>(() => {
  const rows = paths.value.slice(0, 10)
  return {
    tooltip: { ...baseTooltip('item'), formatter: (p: any) => `${p.name}<br/>会话数: ${fmtInt(p.value)}` },
    grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'category', data: rows.map((r) => pathLabel(r.path)).reverse(), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#6b7280', fontSize: 11 } },
    series: [{ type: 'bar', data: rows.map((r) => r.sessions).reverse(), itemStyle: { color: '#3a8fb7', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 18 }],
  }
})
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="section-title">高频购买路径 Top 10</div>
      <EChart :option="option" height="300px" />
    </div>
    <div class="card card-pad">
      <div class="section-title">路径明细</div>
      <el-table :data="paths" size="small" class="dense-table" stripe>
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="path" label="行为路径" min-width="200">
          <template #default="{ row }"><code class="path-code">{{ pathLabel(row.path) }}</code></template>
        </el-table-column>
        <el-table-column label="会话数" width="110" align="right"><template #default="{ row }">{{ fmtInt(row.sessions) }}</template></el-table-column>
        <el-table-column label="用户数" width="110" align="right"><template #default="{ row }">{{ fmtInt(row.users) }}</template></el-table-column>
        <el-table-column label="购买会话" width="110" align="right"><template #default="{ row }">{{ fmtInt(row.buy_sessions) }}</template></el-table-column>
        <el-table-column label="最终购买率" width="120" align="right"><template #default="{ row }">{{ fmtPct(row.final_buy_rate) }}</template></el-table-column>
      </el-table>
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">
        共 {{ fmtInt(data?.total_sessions) }} 个会话 / {{ fmtInt(data?.total_users) }} 用户，{{ fmtInt(data?.distinct_paths) }} 种不同路径。
      </div>
    </div>
  </div>
</template>

<style scoped>
.path-code {
  background: #f1f3f7;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-primary-dark);
}
</style>
