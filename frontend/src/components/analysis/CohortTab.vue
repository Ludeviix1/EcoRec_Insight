<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import type { EChartsOption } from '@/utils/echarts'
import { fmtPct, fmtInt } from '@/utils/format'
import type { Retention } from '@/types'

const loading = ref(false)
const data = ref<Retention | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.cohort()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const cohorts = computed(() => data.value?.cohorts ?? [])
const offsets = computed(() => data.value?.cohort_offsets ?? [1, 3, 7, 14, 30])
const labels = computed(() => ['当日', ...offsets.value.map((o) => '+' + o + '天')])

const chartHeight = computed(() => Math.max(420, cohorts.value.length * 20 + 60) + 'px')

const option = computed<EChartsOption>(() => {
  const rows = cohorts.value
  const dataPts: [number, number, number][] = []
  let max = 0
  rows.forEach((c, y) => {
    const vals = [c.rate_day_0 ?? 0, c.rate_day_1 ?? 0, c.rate_day_3 ?? 0, c.rate_day_7 ?? 0, c.rate_day_14 ?? 0, c.rate_day_30 ?? 0]
    vals.forEach((v, x) => {
      if (v > max) max = v
      dataPts.push([x, rows.length - 1 - y, v])
    })
  })
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `同期群: ${rows[rows.length - 1 - p.value[1]]?.cohort_date?.slice(0, 10)}<br/>规模: ${fmtInt(rows[rows.length - 1 - p.value[1]]?.size)}<br/>${labels.value[p.value[0]]}: ${fmtPct(p.value[2])}`,
      backgroundColor: 'rgba(30,41,59,0.92)',
      borderWidth: 0,
      textStyle: { color: '#f1f5f9', fontSize: 12 },
    },
    grid: { left: 96, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: labels.value, splitArea: { show: false }, axisLabel: { color: '#9ca3af', fontSize: 11 }, axisLine: { lineStyle: { color: '#d1d5db' } } },
    yAxis: { type: 'category', data: rows.map((r) => r.cohort_date.slice(0, 10)).reverse(), axisLabel: { color: '#9ca3af', fontSize: 10 }, axisLine: { lineStyle: { color: '#d1d5db' } } },
    visualMap: { min: 0, max: max || 1, calculable: false, orient: 'horizontal', left: 'center', bottom: 0, show: false, inRange: { color: ['#eef2f9', '#9fb6db', '#3457a8'] } },
    series: [
      {
        type: 'heatmap',
        data: dataPts,
        label: { show: true, color: '#374151', fontSize: 9, formatter: (p: any) => fmtPct(p.value[2], 0) },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.2)' } },
      },
    ],
  }
})

const overall = computed(() => data.value?.overall ?? [])
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="section-title">整体留存率</div>
      <div class="overall-row">
        <div v-for="o in overall" :key="o.offset" class="overall-item">
          <div class="muted" style="font-size: 12px">{{ o.label }}</div>
          <div class="metric-value mono" style="font-size: 22px; color: var(--color-primary)">{{ fmtPct(o.rate) }}</div>
          <div class="muted" style="font-size: 11px">留存 {{ fmtInt(o.retained) }} / {{ fmtInt(o.base) }}</div>
        </div>
      </div>
    </div>
    <div class="card card-pad">
      <div class="section-title">同期群留存矩阵</div>
      <div class="cohort-scroll">
        <EChart :option="option" :height="chartHeight" />
      </div>
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">{{ data?.definition }}</div>
    </div>
  </div>
</template>

<style scoped>
.overall-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}
.overall-item {
  background: #f7f9fc;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  text-align: center;
}
.cohort-scroll {
  max-height: 560px;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
