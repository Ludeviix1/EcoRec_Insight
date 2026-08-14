<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import EChart from '@/components/EChart.vue'
import ChartCard from '@/components/ChartCard.vue'
import PageHeader from '@/components/PageHeader.vue'
import UserPicker from '@/components/UserPicker.vue'
import { usersApi, recommendationsApi, ALGORITHMS, ALGORITHM_LABELS, type Algorithm } from '@/api'
import { PALETTE, baseTooltip, baseGrid, type EChartsOption } from '@/utils/echarts'
import {
  fmtMoneyFull, fmtNum, fmtPct, fmtProb, fmtDate,
  genderLabel, modelLabel, riskLabel, riskTagType, stageTagType,
} from '@/utils/format'
import type { UserProfile, RecResult, RecCompare, RecMetrics, RecItem } from '@/types'

const route = useRoute()
const userId = ref<string>(String(route.query.user ?? ''))
const profile = ref<UserProfile | null>(null)
const recLoading = ref(false)
const recResult = ref<RecResult | null>(null)
const algorithm = ref<Algorithm>('hybrid')
const topK = ref(10)

const compareLoading = ref(false)
const compare = ref<RecCompare | null>(null)

const metricsLoading = ref(false)
const metrics = ref<RecMetrics | null>(null)

async function loadUser(id: string) {
  if (!id) {
    profile.value = null
    recResult.value = null
    compare.value = null
    return
  }
  try {
    profile.value = await usersApi.profile(id)
  } catch {
    profile.value = null
  }
  loadRec()
  loadCompare()
}

// UserPicker 通过 v-model 更新 userId；选中或清空时据此加载
watch(userId, (v) => loadUser(v))

async function loadRec() {
  if (!userId.value) return
  recLoading.value = true
  try {
    recResult.value = await recommendationsApi.recommend(userId.value, algorithm.value, topK.value)
  } catch {
    recResult.value = null
  } finally {
    recLoading.value = false
  }
}

async function loadCompare() {
  if (!userId.value) return
  compareLoading.value = true
  try {
    compare.value = await recommendationsApi.compare(userId.value, undefined, Math.min(topK.value, 10))
  } catch {
    compare.value = null
  } finally {
    compareLoading.value = false
  }
}

async function loadMetrics() {
  metricsLoading.value = true
  try {
    metrics.value = await recommendationsApi.metrics()
  } finally {
    metricsLoading.value = false
  }
}

watch(algorithm, loadRec)
watch(topK, loadRec)
onMounted(() => {
  loadMetrics()
  if (userId.value) loadUser(userId.value)
})

/* ---------- 派生 ---------- */
const recItems = computed<RecItem[]>(() => recResult.value?.items ?? [])
const algorithmRows = computed(() => metrics.value?.algorithms ?? [])
const weightExp = computed(() => metrics.value?.weight_experiment)
const compareAlgos = computed(() => compare.value?.algorithms ?? [])
const compareRankData = computed(() => {
  const results = compare.value?.results ?? {}
  const k = Math.min(topK.value, 10)
  const rows: { rank: number; [key: string]: string | number }[] = []
  for (let i = 0; i < k; i++) {
    const row: { rank: number; [key: string]: string | number } = { rank: i + 1 }
    for (const alg of compareAlgos.value) {
      const item = results[alg]?.items?.[i]
      row[alg] = item ? `${i + 1}.${item.item_name || item.item_id}` : '—'
    }
    rows.push(row)
  }
  return rows
})

const evalBarOption = computed<EChartsOption>(() => {
  const rows = algorithmRows.value
  return {
    color: PALETTE,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(30,41,59,0.92)', borderWidth: 0, textStyle: { color: '#f1f5f9', fontSize: 12 } },
    legend: { top: 0, right: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: '#6b7280', fontSize: 11 } },
    grid: { left: 48, right: 20, top: 30, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => ALGORITHM_LABELS[r.algorithm as Algorithm] || r.algorithm), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      { name: '精确率@K', type: 'bar', data: rows.map((r) => r['precision@k'] ?? 0), itemStyle: { color: '#3457a8', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 22 },
      { name: '召回率@K', type: 'bar', data: rows.map((r) => r['recall@k'] ?? 0), itemStyle: { color: '#4a9d9c', borderRadius: [3, 3, 0, 0] }, barMaxWidth: 22 },
      { name: 'NDCG@K', type: 'line', smooth: true, data: rows.map((r) => r['ndcg@k'] ?? 0), lineStyle: { color: '#d98a2b', width: 2 } },
    ],
  }
})

// 推荐原因：各算法对所有商品返回同一句说明，抽取为公共提示，避免逐卡重复
const sharedReason = computed(() => {
  const reasons = Array.from(new Set(recItems.value.map((it) => it.reason).filter(Boolean)))
  return reasons.length === 1 ? reasons[0] : ''
})
function cardReason(it: RecItem): string {
  return it.reason && it.reason !== sharedReason.value ? it.reason : ''
}
</script>

<template>
  <div>
    <PageHeader title="智能推荐" desc="选择用户 → 查看画像与预测 → 获取推荐 → 切换算法 → 对比评估" />

    <div class="card card-pad mb-16">
      <div class="flex-between wrap gap-12">
        <div class="grow" style="max-width: 480px">
          <UserPicker v-model="userId" placeholder="选择用户，查看其个性化推荐" />
        </div>
        <div class="flex-center gap-8 muted" style="font-size: 12.5px">
          <el-icon><MagicStick /></el-icon>
          <span>已选：{{ userId || '未选择' }}</span>
        </div>
      </div>
    </div>

    <!-- 用户画像 + 预测 -->
    <el-row v-if="profile" :gutter="16" class="mb-16">
      <el-col :xs="24" :lg="9">
        <ChartCard title="用户画像摘要" height="auto">
          <div class="info-grid">
            <div class="info-item"><span class="muted">用户</span><span class="mono">{{ profile.user_id }}</span></div>
            <div class="info-item"><span class="muted">性别 / 年龄</span><span>{{ genderLabel(profile.basic.gender) }} / {{ profile.basic.age }}</span></div>
            <div class="info-item"><span class="muted">城市</span><span>{{ profile.basic.city }}</span></div>
            <div class="info-item"><span class="muted">注册天数</span><span class="mono">{{ profile.basic.register_days }}</span></div>
            <div class="info-item"><span class="muted">消费力</span>
              <el-tag v-if="profile.spending_power" :type="stageTagType(profile.spending_power) as any" size="small" effect="light">{{ profile.spending_power }}</el-tag>
              <span v-else>-</span>
            </div>
            <div class="info-item"><span class="muted">生命周期</span>
              <el-tag v-if="profile.lifecycle_stage" :type="stageTagType(profile.lifecycle_stage) as any" size="small" effect="dark">{{ profile.lifecycle_stage }}</el-tag>
              <span v-else>-</span>
            </div>
            <div class="info-item"><span class="muted">RFM 分群</span>
              <el-tag v-if="profile.rfm" type="primary" size="small" effect="dark">{{ profile.rfm.segment }} / {{ profile.rfm.rfm_score }}</el-tag>
              <span v-else>-</span>
            </div>
            <div class="info-item"><span class="muted">累计消费</span><span class="mono" style="color: var(--color-primary); font-weight: 600">{{ fmtMoneyFull(profile.purchase?.gmv) }}</span></div>
          </div>
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="15">
        <ChartCard title="购买 / 流失预测" height="auto">
          <div class="pred-row">
            <div class="pred-block">
              <div class="flex-between">
                <span class="muted" style="font-size: 12.5px">未来 {{ profile.predictions.purchase?.label_days ?? 7 }} 天购买概率</span>
                <span class="pred-value" :class="{ 'is-high': (profile.predictions.purchase?.purchase_probability ?? 0) >= 0.5 }">
                  {{ fmtProb(profile.predictions.purchase?.purchase_probability) }}
                </span>
              </div>
              <el-progress :percentage="Math.round((profile.predictions.purchase?.purchase_probability ?? 0) * 100)" :stroke-width="10" :show-text="false"
                :color="(profile.predictions.purchase?.purchase_probability ?? 0) >= 0.5 ? '#c0504d' : '#3457a8'" class="mt-8" />
              <div class="muted mt-8" style="font-size: 11.5px">模型 {{ modelLabel(profile.predictions.purchase?.model) }} · 观察截止 {{ fmtDate(profile.predictions.purchase?.obs_end) }}</div>
            </div>
            <div class="pred-block">
              <div class="flex-between">
                <span class="muted" style="font-size: 12.5px">未来 30 天流失概率</span>
                <span class="pred-value" :class="{ 'is-high': (profile.predictions.churn?.churn_probability ?? 0) >= 0.5 }">
                  {{ fmtProb(profile.predictions.churn?.churn_probability) }}
                </span>
              </div>
              <el-progress :percentage="Math.round((profile.predictions.churn?.churn_probability ?? 0) * 100)" :stroke-width="10" :show-text="false"
                :color="(profile.predictions.churn?.churn_probability ?? 0) >= 0.5 ? '#c0504d' : '#4a9d9c'" class="mt-8" />
              <div class="flex-between mt-8">
                <span class="muted" style="font-size: 11.5px">观察截止 {{ fmtDate(profile.predictions.churn?.obs_end) }}</span>
                <el-tag v-if="profile.predictions.churn" :type="riskTagType(profile.predictions.churn.risk_level) as any" size="small" effect="dark">
                  风险：{{ riskLabel(profile.predictions.churn.risk_level) }}
                </el-tag>
              </div>
            </div>
          </div>
        </ChartCard>
      </el-col>
    </el-row>

    <!-- 推荐结果 -->
    <ChartCard title="个性化推荐结果" subtitle="切换算法查看不同推荐与推荐原因" height="auto" class="mb-16">
      <template #head>
        <div class="flex-center gap-12">
          <el-select v-model="algorithm" size="small" style="width: 170px">
            <el-option v-for="a in ALGORITHMS" :key="a" :label="ALGORITHM_LABELS[a]" :value="a" />
          </el-select>
          <el-input-number v-model="topK" :min="5" :max="20" :step="5" size="small" controls-position="right" style="width: 110px" />
        </div>
      </template>
      <el-empty v-if="!userId" description="请先选择用户" />
      <div v-else v-loading="recLoading">
        <el-alert v-if="recResult?.error" type="warning" :closable="false" :title="recResult.error" class="mb-12" />
        <el-empty v-else-if="!recItems.length" description="暂无推荐结果" />
        <div v-else>
          <div v-if="sharedReason" class="rec-reason-note">
            <span class="rec-reason-note__label">推荐依据</span>{{ sharedReason }}
          </div>
          <div class="rec-grid">
            <div v-for="(it, i) in recItems" :key="it.item_id" class="rec-card">
              <div class="flex-between">
                <span class="rec-rank">#{{ i + 1 }}</span>
                <span class="rec-score mono">{{ fmtNum(it.score, 4) }}</span>
              </div>
              <div class="rec-name" :title="it.item_name">{{ it.item_name || it.item_id }}</div>
              <div class="flex-between mt-8">
                <span class="muted" style="font-size: 11.5px">{{ it.brand || '—' }}</span>
                <span class="mono" style="font-size: 13px; color: var(--color-primary)">{{ fmtMoneyFull(it.price) }}</span>
              </div>
              <div v-if="cardReason(it)" class="rec-reason">{{ cardReason(it) }}</div>
            </div>
          </div>
        </div>
      </div>
    </ChartCard>

    <!-- 多算法对比 -->
    <ChartCard title="多算法对比" subtitle="同一用户下 5 种算法的 Top-K 命中差异" height="auto" class="mb-16">
      <div v-if="!userId" class="muted" style="padding: 12px 0">请先选择用户</div>
      <div v-else v-loading="compareLoading">
        <el-table :data="compareRankData" size="small" class="dense-table" stripe>
          <el-table-column label="排名" prop="rank" width="70" align="center" />
          <el-table-column v-for="alg in compareAlgos" :key="alg" :label="ALGORITHM_LABELS[alg as Algorithm] || alg" min-width="150">
            <template #default="{ row }">
              <span class="mono" style="font-size: 12px">{{ row[alg] }}</span>
            </template>
          </el-table-column>
          <template #empty><el-empty description="暂无对比数据" :image-size="70" /></template>
        </el-table>
      </div>
    </ChartCard>

    <!-- 推荐评估 -->
    <ChartCard title="推荐评估（离线）" subtitle="严格时间切分：历史→训练，未来→测试" height="auto">
      <template #head>
        <el-tag v-if="metrics" size="small" effect="plain" type="info">K={{ metrics.k }} · 测试集比例 {{ fmtPct(metrics.test_ratio, 0) }} · 基准算法：{{ ALGORITHM_LABELS[metrics.baseline as Algorithm] || metrics.baseline }}</el-tag>
      </template>
      <div v-loading="metricsLoading">
        <el-alert v-if="metrics?.conclusion" type="success" :closable="false" show-icon class="mb-12">
          <template #title>{{ metrics.conclusion }}</template>
        </el-alert>

        <el-row :gutter="16">
          <el-col :xs="24" :lg="14">
            <el-table :data="algorithmRows" size="small" class="dense-table" stripe>
              <el-table-column label="算法" min-width="120">
                <template #default="{ row }">
                  <span style="font-weight: 600">{{ ALGORITHM_LABELS[row.algorithm as Algorithm] || row.algorithm }}</span>
                </template>
              </el-table-column>
              <el-table-column label="精确率@K" prop="precision@k" width="100" align="right">
                <template #default="{ row }">{{ fmtNum(row['precision@k'] ?? 0, 4) }}</template>
              </el-table-column>
              <el-table-column label="召回率@K" prop="recall@k" width="100" align="right">
                <template #default="{ row }">{{ fmtNum(row['recall@k'] ?? 0, 4) }}</template>
              </el-table-column>
              <el-table-column label="NDCG@K" prop="ndcg@k" width="100" align="right">
                <template #default="{ row }">
                  <span :style="row['ndcg@k'] === Math.max(...algorithmRows.map((r) => r['ndcg@k'] ?? 0)) ? 'color: var(--color-primary); font-weight: 600' : ''">
                    {{ fmtNum(row['ndcg@k'] ?? 0, 4) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="命中率@K" prop="hit_rate@k" width="100" align="right">
                <template #default="{ row }">{{ fmtNum(row['hit_rate@k'] ?? 0, 4) }}</template>
              </el-table-column>
              <el-table-column label="覆盖率" prop="coverage@k" width="100" align="right">
                <template #default="{ row }">{{ fmtNum(row['coverage@k'] ?? 0, 4) }}</template>
              </el-table-column>
            </el-table>
          </el-col>
          <el-col :xs="24" :lg="10">
            <EChart :option="evalBarOption" height="260px" />
          </el-col>
        </el-row>

        <el-divider />
        <div class="section-title">行为权重实验结论</div>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="最优实验">{{ weightExp?.best_experiment || '-' }}</el-descriptions-item>
          <el-descriptions-item label="最优权重">
            <template v-if="weightExp?.best_weights">
              <el-tag v-for="(v, k) in weightExp.best_weights" :key="k" size="small" effect="light" class="mr-8" type="primary">{{ ALGORITHM_LABELS[k as Algorithm] || k }}：{{ v }}</el-tag>
            </template>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="选择依据">{{ weightExp?.selection_criterion || '-' }}</el-descriptions-item>
          <el-descriptions-item v-if="weightExp?.note" label="说明">{{ weightExp.note }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </ChartCard>
  </div>
</template>

<style scoped>
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.info-item .muted {
  font-size: 11.5px;
}
.pred-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
@media (max-width: 768px) {
  .pred-row {
    grid-template-columns: 1fr;
  }
}
.pred-block {
  background: #f7f9fc;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
}
.pred-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-success);
  font-variant-numeric: tabular-nums;
}
.pred-value.is-high {
  color: var(--color-danger);
}
.rec-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.rec-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  background: #fff;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.rec-card:hover {
  border-color: var(--color-primary-light);
  box-shadow: var(--shadow-card);
}
.rec-rank {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary);
  background: var(--el-color-primary-light-9);
  padding: 1px 7px;
  border-radius: 10px;
}
.rec-score {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.rec-name {
  font-size: 13.5px;
  font-weight: 600;
  margin-top: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rec-reason {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--color-border-light);
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.rec-reason-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  margin-bottom: 14px;
}
.rec-reason-note__label {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--color-primary);
}
.mr-8 {
  margin-right: 8px;
}
</style>
