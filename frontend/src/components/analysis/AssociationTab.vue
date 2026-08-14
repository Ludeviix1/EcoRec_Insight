<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtNum } from '@/utils/format'
import type { AssociationResponse, AssociationRule } from '@/types'

const loading = ref(false)
const data = ref<AssociationResponse | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.association()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const itemRules = computed(() => data.value?.item_rules ?? [])
const categoryRules = computed(() => data.value?.category_rules ?? [])

function join(items: string | string[] | undefined): string {
  if (!items) return '-'
  return Array.isArray(items) ? items.join(' + ') : String(items)
}

const scatterOption = computed<EChartsOption>(() => {
  const rows = categoryRules.value
  return {
    color: ['#3457a8'],
    tooltip: baseTooltip('item'),
    grid: { left: 48, right: 20, top: 16, bottom: 36, containLabel: true },
    xAxis: { type: 'value', name: '置信度', min: 0, splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'value', name: '提升度', min: 1, splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      {
        type: 'scatter',
        symbolSize: (val: number[]) => 10 + Math.min(val[0] * 4000, 40),
        data: rows.map((r) => [r.confidence, r.lift]),
        label: { show: true, position: 'top', fontSize: 10, color: '#6b7280', formatter: (p: any) => `${join(rows[p.dataIndex]?.antecedents)} → ${join(rows[p.dataIndex]?.consequents)}` },
      },
    ],
  }
})

function ruleColumns(rows: AssociationRule[]) {
  return rows
}
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="section-title">关联规则散点（置信度 × 提升度）</div>
      <el-empty v-if="!categoryRules.length && !itemRules.length" description="当前阈值下未挖掘到关联规则" :image-size="80" />
      <EChart v-else :option="scatterOption" height="280px" />
    </div>

    <div class="card card-pad mb-16">
      <div class="section-title">商品关联规则</div>
      <el-table v-if="itemRules.length" :data="itemRules" size="small" class="dense-table" stripe>
        <el-table-column label="前项 A" min-width="180"><template #default="{ row }">{{ join(row.antecedents) }}</template></el-table-column>
        <el-table-column label="后项 B" min-width="180"><template #default="{ row }">{{ join(row.consequents) }}</template></el-table-column>
        <el-table-column label="支持度" width="100" align="right"><template #default="{ row }">{{ fmtNum(row.support, 4) }}</template></el-table-column>
        <el-table-column label="置信度" width="100" align="right"><template #default="{ row }">{{ fmtNum(row.confidence, 4) }}</template></el-table-column>
        <el-table-column label="提升度" width="100" align="right"><template #default="{ row }">{{ fmtNum(row.lift, 3) }}</template></el-table-column>
        <el-table-column label="次数" width="90" align="right"><template #default="{ row }">{{ fmtInt(row.count) }}</template></el-table-column>
      </el-table>
      <el-empty v-else description="无商品关联规则" :image-size="70" />
    </div>

    <div class="card card-pad">
      <div class="section-title">分类关联规则</div>
      <el-table v-if="categoryRules.length" :data="categoryRules" size="small" class="dense-table" stripe>
        <el-table-column label="前项 A" min-width="160"><template #default="{ row }">{{ join(row.antecedents) }}</template></el-table-column>
        <el-table-column label="后项 B" min-width="160"><template #default="{ row }">{{ join(row.consequents) }}</template></el-table-column>
        <el-table-column label="支持度" width="100" align="right"><template #default="{ row }">{{ fmtNum(row.support, 4) }}</template></el-table-column>
        <el-table-column label="置信度" width="100" align="right"><template #default="{ row }">{{ fmtNum(row.confidence, 4) }}</template></el-table-column>
        <el-table-column label="提升度" width="100" align="right"><template #default="{ row }">{{ fmtNum(row.lift, 3) }}</template></el-table-column>
        <el-table-column label="次数" width="90" align="right"><template #default="{ row }">{{ fmtInt(row.count) }}</template></el-table-column>
      </el-table>
      <el-empty v-else description="无分类关联规则" :image-size="70" />
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">
        {{ data?.definition }}
      </div>
    </div>
  </div>
</template>
