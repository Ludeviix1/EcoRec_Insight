<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import EChart from '@/components/EChart.vue'
import ChartCard from '@/components/ChartCard.vue'
import StatCard from '@/components/StatCard.vue'
import PageHeader from '@/components/PageHeader.vue'
import { modelsApi, ALGORITHM_LABELS, type Algorithm } from '@/api'
import { PALETTE, baseTooltip, baseGrid, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtNum, fmtProb, riskLabel, riskTagType, modelLabel } from '@/utils/format'
import type { ModelDetail, ModelMetrics, ModelsMetrics, ChurnPrediction, ModelTestScore } from '@/types'

const loading = ref(false)
const purchase = ref<ModelDetail | null>(null)
const churn = ref<ModelDetail | null>(null)
const summary = ref<ModelsMetrics | null>(null)

async function load() {
  loading.value = true
  const [p, c, s] = await Promise.allSettled([modelsApi.purchase(), modelsApi.churn(50), modelsApi.metrics()])
  if (p.status === 'fulfilled') purchase.value = p.value
  if (c.status === 'fulfilled') churn.value = c.value
  if (s.status === 'fulfilled') summary.value = s.value
  loading.value = false
}
onMounted(load)

/* ---------- 工具 ---------- */
function metricRows(metrics: ModelMetrics | undefined): { name: string; m: ModelTestScore }[] {
  if (!metrics) return []
  return Object.entries(metrics).map(([name, v]) => ({ name, m: (v as any)?.test ?? {} }))
}

const bestModelKey = computed(() => purchase.value?.best_model?.model ?? '')
const bestChurnKey = computed(() => churn.value?.best_model?.model ?? '')
const bestModelName = computed(() => modelLabel(bestModelKey.value || '-'))
const bestChurnName = computed(() => modelLabel(bestChurnKey.value || '-'))

function importanceOption(rows: { name: string; value: number }[]): EChartsOption {
  const data = rows.filter((r) => r.value !== 0)
  return {
    color: ['#3457a8'],
    tooltip: baseTooltip('item'),
    grid: { left: 8, right: 30, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 10 } },
    yAxis: { type: 'category', data: data.map((r) => r.name).reverse(), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#6b7280', fontSize: 10 } },
    series: [{ type: 'bar', data: data.map((r) => r.value).reverse(), itemStyle: { color: '#3457a8', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 14 }],
  }
}

const purchaseImportanceOption = computed<EChartsOption>(() =>
  importanceOption((purchase.value?.feature_importance ?? []).slice(0, 12).map((r) => ({ name: r.feature, value: r.importance ?? r.abs_coef ?? r.coef ?? 0 }))),
)
const churnImportanceOption = computed<EChartsOption>(() =>
  importanceOption((churn.value?.feature_importance ?? []).slice(0, 12).map((r) => ({ name: r.feature, value: r.importance ?? r.abs_coef ?? r.coef ?? 0 }))),
)

function compareOption(rows: { name: string; m: ModelTestScore }[]): EChartsOption {
  return {
    color: PALETTE,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(30,41,59,0.92)', borderWidth: 0, textStyle: { color: '#f1f5f9', fontSize: 12 } },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: '#6b7280', fontSize: 11 } },
    grid: baseGrid(),
    xAxis: { type: 'category', data: rows.map((r) => r.name), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 1, splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      { name: '精确率', type: 'bar', data: rows.map((r) => r.m.precision ?? 0), itemStyle: { color: '#3457a8', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 22 },
      { name: '召回率', type: 'bar', data: rows.map((r) => r.m.recall ?? 0), itemStyle: { color: '#4a9d9c', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 22 },
      { name: 'F1', type: 'bar', data: rows.map((r) => r.m.f1 ?? 0), itemStyle: { color: '#d98a2b', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 22 },
      { name: 'AUC', type: 'line', smooth: true, data: rows.map((r) => r.m.roc_auc ?? 0), lineStyle: { color: '#8e6fc0', width: 2 } },
    ],
  }
}

const purchaseCompareOption = computed<EChartsOption>(() => compareOption(metricRows(purchase.value?.metrics)))
const churnCompareOption = computed<EChartsOption>(() => compareOption(metricRows(churn.value?.metrics)))

const churnPreds = computed<ChurnPrediction[]>(() => churn.value?.predictions ?? [])

const summaryRows = computed(() => {
  const rows: { task: string; model: string; roc_auc: number; pr_auc: number; f1: number; n_samples: number }[] = []
  const push = (task: string, m: Record<string, ModelTestScore> | undefined) => {
    for (const [name, score] of Object.entries(m ?? {})) {
      rows.push({ task, model: name, roc_auc: score.roc_auc ?? 0, pr_auc: score.pr_auc ?? 0, f1: score.f1 ?? 0, n_samples: score.n_samples ?? 0 })
    }
  }
  push('购买', summary.value?.purchase)
  push('流失', summary.value?.churn)
  return rows
})

const kpis = computed(() => [
  { label: '购买预测最佳模型', value: bestModelName.value, accent: '#3457a8', icon: 'Cpu' },
  { label: '流失预测最佳模型', value: bestChurnName.value, accent: '#4a9d9c', icon: 'Cpu' },
  { label: '购买 ROC-AUC', value: fmtNum((purchase.value?.best_model?.test as any)?.roc_auc ?? 0, 3), accent: '#2f9e6e', icon: 'TrendCharts' },
  { label: '流失 ROC-AUC', value: fmtNum((churn.value?.best_model?.test as any)?.roc_auc ?? 0, 3), accent: '#c0504d', icon: 'TrendCharts' },
])
</script>

<template>
  <div v-loading="loading">
    <PageHeader title="预测模型" desc="购买预测与流失预测：时间切分防泄漏 · 特征重要性 · 模型对比" />

    <div class="stat-row mb-16">
      <StatCard v-for="k in kpis" :key="k.label" :label="k.label" :value="k.value" :accent="k.accent" :icon="k.icon" />
    </div>

    <!-- 购买预测 -->
    <ChartCard title="购买预测模型" subtitle="观察窗口特征 → 未来 7 天是否购买" height="auto" class="mb-16">
      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <div class="section-title">模型测试指标对比</div>
          <el-table :data="metricRows(purchase?.metrics)" size="small" class="dense-table" stripe>
            <el-table-column label="模型" min-width="130">
              <template #default="{ row }">
                <span style="font-weight: 600">{{ modelLabel(row.name) }}</span>
                <el-tag v-if="row.name === bestModelKey" size="small" type="success" effect="light" class="ml-8">最佳</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="AUC" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.m.roc_auc ?? 0, 3) }}</template></el-table-column>
            <el-table-column label="PR-AUC" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.m.pr_auc ?? 0, 3) }}</template></el-table-column>
            <el-table-column label="F1" width="80" align="right"><template #default="{ row }">{{ fmtNum(row.m.f1 ?? 0, 3) }}</template></el-table-column>
            <el-table-column label="召回率" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.m.recall ?? 0, 3) }}</template></el-table-column>
          </el-table>
          <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">
            {{ purchase?.leakage_guard }}<br />{{ purchase?.description }}
          </div>
        </el-col>
        <el-col :xs="24" :lg="6">
          <div class="section-title">指标对比</div>
          <EChart :option="purchaseCompareOption" height="280px" />
        </el-col>
        <el-col :xs="24" :lg="8">
          <div class="section-title">特征重要性 Top</div>
          <EChart :option="purchaseImportanceOption" height="280px" />
        </el-col>
      </el-row>
    </ChartCard>

    <!-- 流失预测 -->
    <ChartCard title="流失预测模型" subtitle="观察窗口活跃用户 → 未来 30 天是否流失" height="auto" class="mb-16">
      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <div class="section-title">模型测试指标对比</div>
          <el-table :data="metricRows(churn?.metrics)" size="small" class="dense-table" stripe>
            <el-table-column label="模型" min-width="130">
              <template #default="{ row }">
                <span style="font-weight: 600">{{ modelLabel(row.name) }}</span>
                <el-tag v-if="row.name === bestChurnKey" size="small" type="success" effect="light" class="ml-8">最佳</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="AUC" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.m.roc_auc ?? 0, 3) }}</template></el-table-column>
            <el-table-column label="PR-AUC" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.m.pr_auc ?? 0, 3) }}</template></el-table-column>
            <el-table-column label="F1" width="80" align="right"><template #default="{ row }">{{ fmtNum(row.m.f1 ?? 0, 3) }}</template></el-table-column>
            <el-table-column label="召回率" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.m.recall ?? 0, 3) }}</template></el-table-column>
          </el-table>
          <div class="muted mt-12" style="font-size: 12px; line-height: 1.6">{{ churn?.leakage_guard }}</div>
        </el-col>
        <el-col :xs="24" :lg="6">
          <div class="section-title">指标对比</div>
          <EChart :option="churnCompareOption" height="280px" />
        </el-col>
        <el-col :xs="24" :lg="8">
          <div class="section-title">特征重要性 Top</div>
          <EChart :option="churnImportanceOption" height="280px" />
        </el-col>
      </el-row>
      <el-divider />
      <div class="section-title">高风险流失用户 Top {{ churnPreds.length }}</div>
      <div class="risk-list">
        <div v-for="p in churnPreds.slice(0, 20)" :key="p.user_id" class="risk-item">
          <span class="mono" style="font-size: 12.5px; width: 90px">{{ p.user_id }}</span>
          <el-progress
            :percentage="Math.round(p.churn_probability * 100)"
            :color="p.churn_probability >= 0.7 ? '#c0504d' : p.churn_probability >= 0.5 ? '#d98a2b' : '#4a9d9c'"
            :stroke-width="8"
            :show-text="false"
            style="flex: 1"
          />
          <span class="mono" style="font-size: 12px; width: 70px; text-align: right">{{ fmtProb(p.churn_probability) }}</span>
          <el-tag :type="riskTagType(p.risk_level) as any" size="small" effect="dark" style="width: 74px; justify-content: center">{{ riskLabel(p.risk_level) }}</el-tag>
        </div>
      </div>
    </ChartCard>

    <!-- 汇总 -->
    <ChartCard title="预测 + 推荐评估汇总" height="auto">
      <el-row :gutter="16">
        <el-col :xs="24" :lg="12">
          <div class="section-title">购买 / 流失模型 Test 集对比</div>
          <el-table :data="summaryRows" size="small" class="dense-table" stripe>
            <el-table-column label="任务" prop="task" min-width="80" />
            <el-table-column label="模型" min-width="150">
              <template #default="{ row }">{{ modelLabel(row.model) }}</template>
            </el-table-column>
            <el-table-column label="AUC" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.roc_auc, 3) }}</template></el-table-column>
            <el-table-column label="PR-AUC" width="90" align="right"><template #default="{ row }">{{ fmtNum(row.pr_auc, 3) }}</template></el-table-column>
            <el-table-column label="F1" width="80" align="right"><template #default="{ row }">{{ fmtNum(row.f1, 3) }}</template></el-table-column>
            <el-table-column label="样本" width="80" align="right"><template #default="{ row }">{{ fmtInt(row.n_samples) }}</template></el-table-column>
          </el-table>
        </el-col>
        <el-col :xs="24" :lg="12">
          <div class="section-title">推荐算法评估</div>
          <el-table :data="summary?.recommendation?.algorithms ?? []" size="small" class="dense-table" stripe>
            <el-table-column label="算法" min-width="110">
              <template #default="{ row }">{{ ALGORITHM_LABELS[row.algorithm as Algorithm] || row.algorithm }}</template>
            </el-table-column>
            <el-table-column label="精确率@K" prop="precision@k" width="90" align="right"><template #default="{ row }">{{ fmtNum(row['precision@k'] ?? 0, 4) }}</template></el-table-column>
            <el-table-column label="NDCG@K" prop="ndcg@k" width="90" align="right"><template #default="{ row }">{{ fmtNum(row['ndcg@k'] ?? 0, 4) }}</template></el-table-column>
            <el-table-column label="覆盖率" prop="coverage@k" width="90" align="right"><template #default="{ row }">{{ fmtNum(row['coverage@k'] ?? 0, 4) }}</template></el-table-column>
          </el-table>
          <el-alert v-if="summary?.recommendation?.conclusion" type="success" :closable="false" show-icon class="mt-12">
            <template #title>{{ summary.recommendation.conclusion }}</template>
          </el-alert>
        </el-col>
      </el-row>
    </ChartCard>
  </div>
</template>

<style scoped>
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}
.ml-8 {
  margin-left: 8px;
}
.risk-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.risk-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
