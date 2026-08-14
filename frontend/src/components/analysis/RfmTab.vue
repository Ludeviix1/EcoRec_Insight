<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { PALETTE, baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtMoney, fmtPct } from '@/utils/format'
import type { RfmResponse } from '@/types'

const loading = ref(false)
const data = ref<RfmResponse | null>(null)
const metric = ref<'count' | 'gmv'>('count')

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.rfm()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const segments = computed(() => data.value?.segment_distribution ?? [])

const option = computed<EChartsOption>(() => {
  const rows = segments.value
  return {
    color: PALETTE,
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `${p.name}<br/>${metric.value === 'count' ? '人数' : '销售额'}: ${metric.value === 'count' ? fmtInt(p.value) : fmtMoney(p.value)}<br/>占比: ${fmtPct(p.percent / 100)}`,
      backgroundColor: 'rgba(30,41,59,0.92)',
      borderWidth: 0,
      textStyle: { color: '#f1f5f9', fontSize: 12 },
    },
    legend: { bottom: 0, icon: 'circle', itemWidth: 8, textStyle: { color: '#6b7280', fontSize: 12 } },
    series: [
      {
        type: 'pie',
        radius: ['40%', '68%'],
        center: ['50%', '44%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { formatter: '{b}\n{d}%', color: '#4b5563', fontSize: 11 },
        data: rows.map((r) => ({ name: r.segment, value: metric.value === 'count' ? r.count : r.gmv })),
      },
    ],
  }
})
</script>

<template>
  <div v-loading="loading">
    <el-row :gutter="16">
      <el-col :xs="24" :md="11">
        <div class="card card-pad">
          <div class="section-title">RFM 分群占比</div>
          <el-radio-group v-model="metric" size="small" class="mb-12">
            <el-radio-button value="count">按人数</el-radio-button>
            <el-radio-button value="gmv">按销售额</el-radio-button>
          </el-radio-group>
          <EChart :option="option" height="320px" />
        </div>
      </el-col>
      <el-col :xs="24" :md="13">
        <div class="card card-pad">
          <div class="section-title">分群明细</div>
          <el-table :data="segments" size="small" class="dense-table" stripe>
            <el-table-column prop="segment" label="分群" min-width="110" />
            <el-table-column label="人数" width="100" align="right">
              <template #default="{ row }">{{ fmtInt(row.count) }}</template>
            </el-table-column>
            <el-table-column label="占比" width="100" align="right">
              <template #default="{ row }">{{ fmtPct(row.ratio) }}</template>
            </el-table-column>
            <el-table-column label="销售额" width="140" align="right">
              <template #default="{ row }">{{ fmtMoney(row.gmv) }}</template>
            </el-table-column>
          </el-table>
          <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">
            RFM 基于 R（最近购买）/ F（频次）/ M（金额）打分分群；购买用户共 {{ fmtInt(data?.total_buying_users) }} 人。
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>
