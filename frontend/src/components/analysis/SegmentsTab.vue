<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import { analysisApi } from '@/api'
import { PALETTE, baseTooltip, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtPct, fmtNum } from '@/utils/format'
import type { SegmentsResponse } from '@/types'

const loading = ref(false)
const data = ref<SegmentsResponse | null>(null)

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.segments()
  } finally {
    loading.value = false
  }
}
onMounted(load)

const clusters = computed(() => data.value?.clusters ?? [])
const features = computed(() => data.value?.features ?? [])

const radarOption = computed<EChartsOption>(() => {
  const rows = clusters.value
  const feats = features.value
  const indicators = feats.map((f) => {
    let max = 0
    rows.forEach((c) => {
      const v = Math.abs((c.feature_means as Record<string, number>)[f] ?? 0)
      if (v > max) max = v
    })
    return { name: f, max: max || 1 }
  })
  return {
    color: PALETTE,
    tooltip: { trigger: 'item', backgroundColor: 'rgba(30,41,59,0.92)', borderWidth: 0, textStyle: { color: '#f1f5f9', fontSize: 12 } },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: '#6b7280', fontSize: 11 } },
    radar: {
      indicator: indicators,
      radius: '62%',
      center: ['50%', '46%'],
      axisName: { color: '#6b7280', fontSize: 11 },
      splitArea: { areaStyle: { color: ['#fafbfd', '#f3f5f9'] } },
    },
    series: [
      {
        type: 'radar',
        symbolSize: 3,
        data: rows.map((c) => ({
          name: c.cluster_name,
          value: features.value.map((f) => (c.feature_means as Record<string, number>)[f] ?? 0),
        })),
        areaStyle: { opacity: 0.12 },
      },
    ],
  }
})
</script>

<template>
  <div v-loading="loading">
    <div class="card card-pad mb-16">
      <div class="section-title">用户分群特征雷达（K 均值）</div>
      <EChart :option="radarOption" height="340px" />
    </div>
    <div class="card card-pad">
      <div class="section-title">分群解读</div>
      <el-row :gutter="14">
        <el-col v-for="c in clusters" :key="c.cluster_id" :xs="24" :sm="12" :md="6" class="mb-12">
          <div class="cluster-card">
            <div class="flex-between">
              <span class="cluster-name">{{ c.cluster_name }}</span>
              <el-tag size="small" effect="light" type="info">{{ fmtPct(c.ratio) }}</el-tag>
            </div>
            <div class="cluster-size mono">{{ fmtInt(c.size) }} 人</div>
            <div class="cluster-desc">{{ c.interpretation }}</div>
          </div>
        </el-col>
      </el-row>
      <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">
        {{ data?.definition }}（随机种子 {{ data?.random_state }}，{{ data?.n_clusters }} 类）
      </div>
    </div>
  </div>
</template>

<style scoped>
.cluster-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  background: #fff;
  height: 100%;
}
.cluster-name {
  font-weight: 600;
  font-size: 13.5px;
}
.cluster-size {
  color: var(--color-primary);
  font-weight: 600;
  margin: 8px 0;
  font-size: 15px;
}
.cluster-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}
</style>
