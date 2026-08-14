<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EChart from '@/components/EChart.vue'
import ChartCard from '@/components/ChartCard.vue'
import StatCard from '@/components/StatCard.vue'
import PageHeader from '@/components/PageHeader.vue'
import { usersApi, ALGORITHMS, ALGORITHM_LABELS, type Algorithm } from '@/api'
import { PALETTE, baseGrid, baseTooltip, type EChartsOption } from '@/utils/echarts'
import {
  fmtInt, fmtMoney, fmtMoneyFull, fmtPct, fmtProb, fmtNum, fmtDate, fmtDateTime,
  behaviorLabel, genderLabel, channelLabel, deviceLabel, orderStatusLabel, payMethodLabel,
  modelLabel, riskLabel, riskTagType, stageTagType, weekdayLabel,
} from '@/utils/format'
import type { UserProfile, UserBehavior, Order, RecResult, RecItem } from '@/types'

const route = useRoute()
const router = useRouter()
const userId = computed(() => String(route.params.id))

const loading = ref(false)
const profile = ref<UserProfile | null>(null)
const behaviors = ref<UserBehavior[]>([])
const orders = ref<Order[]>([])
const recLoading = ref(false)
const recResult = ref<RecResult | null>(null)
const algorithm = ref<Algorithm>('hybrid')
const topK = ref(10)

async function loadProfile() {
  loading.value = true
  try {
    const [p, bh, od] = await Promise.allSettled([
      usersApi.profile(userId.value),
      usersApi.behaviors(userId.value, 100),
      usersApi.orders(userId.value),
    ])
    if (p.status === 'fulfilled') profile.value = p.value
    if (bh.status === 'fulfilled') behaviors.value = bh.value.items
    if (od.status === 'fulfilled') orders.value = od.value.items
  } finally {
    loading.value = false
  }
  loadRec()
}

async function loadRec() {
  recLoading.value = true
  try {
    recResult.value = await usersApi.recommendations(userId.value, algorithm.value, topK.value)
  } catch {
    recResult.value = null
  } finally {
    recLoading.value = false
  }
}

watch(algorithm, loadRec)
watch(topK, loadRec)
watch(userId, loadProfile)
onMounted(loadProfile)

/* ---------- 派生数据 ---------- */
const behaviorStats = computed(() => {
  const b = profile.value?.behavior
  return [
    { label: '浏览', value: fmtInt(b?.pv), accent: '#6ba3d0' },
    { label: '点击', value: fmtInt(b?.click), accent: '#4a9d9c' },
    { label: '收藏', value: fmtInt(b?.collect), accent: '#d98a2b' },
    { label: '加购', value: fmtInt(b?.cart), accent: '#8e6fc0' },
    { label: '购买', value: fmtInt(b?.buy), accent: '#c0504d' },
    { label: '活跃天数', value: fmtInt(b?.active_days), accent: '#3457a8' },
  ]
})
const purchaseStats = computed(() => {
  const p = profile.value?.purchase
  return [
    { label: '订单数', value: fmtInt(p?.order_count), accent: '#3457a8' },
    { label: '累计消费', value: fmtMoney(p?.gmv), hint: fmtMoneyFull(p?.gmv), accent: '#2f9e6e' },
    { label: '客单价', value: fmtMoney(p?.aov), accent: '#3a8fb7' },
  ]
})

const prefCategoryOption = computed<EChartsOption>(() => {
  const rows = profile.value?.preferred_categories ?? []
  return {
    color: PALETTE,
    tooltip: baseTooltip('item'),
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'category', data: rows.map((r) => r.value).reverse(), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [{ type: 'bar', data: rows.map((r) => r.count).reverse(), itemStyle: { color: '#3457a8', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 16 }],
  }
})
const prefBrandOption = computed<EChartsOption>(() => {
  const rows = profile.value?.preferred_brands ?? []
  return {
    color: PALETTE,
    tooltip: baseTooltip('item'),
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'category', data: rows.map((r) => r.value).reverse(), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [{ type: 'bar', data: rows.map((r) => r.count).reverse(), itemStyle: { color: '#4a9d9c', borderRadius: [0, 3, 3, 0] }, barMaxWidth: 16 }],
  }
})

const recItems = computed<RecItem[]>(() => recResult.value?.items ?? [])
const hasRecError = computed(() => !!recResult.value?.error)

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
  <div v-loading="loading">
    <PageHeader :title="`用户 ${userId}`" desc="用户画像 · RFM / 生命周期 · 购买 / 流失预测 · 个性化推荐">
      <el-button @click="router.push('/users')"><el-icon><ArrowLeft /></el-icon>返回列表</el-button>
      <el-button type="primary" @click="router.push({ path: '/recommendations', query: { user: userId } })">
        前往推荐实验<el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </PageHeader>

    <!-- 行为 & 购买 KPI -->
    <div class="stat-row">
      <StatCard v-for="s in behaviorStats" :key="s.label" :label="s.label" :value="s.value" :accent="s.accent" />
    </div>
    <div class="stat-row mt-16">
      <StatCard v-for="s in purchaseStats" :key="s.label" :label="s.label" :value="s.value" :hint="s.hint" :accent="s.accent" />
    </div>

    <el-row :gutter="16" class="mt-16">
      <!-- 基础信息 + 标签 -->
      <el-col :xs="24" :lg="8">
        <ChartCard title="基础信息与分群标签" height="auto">
          <div class="info-grid">
            <div class="info-item"><span class="muted">年龄</span><span class="mono">{{ profile?.basic.age ?? '-' }}</span></div>
            <div class="info-item"><span class="muted">性别</span><span>{{ genderLabel(profile?.basic.gender) }}</span></div>
            <div class="info-item"><span class="muted">城市</span><span>{{ profile?.basic.city ?? '-' }}</span></div>
            <div class="info-item"><span class="muted">注册天数</span><span class="mono">{{ profile?.basic.register_days ?? '-' }}</span></div>
            <div class="info-item"><span class="muted">渠道</span><span>{{ channelLabel(profile?.channel) }}</span></div>
            <div class="info-item"><span class="muted">设备</span><span>{{ deviceLabel(profile?.device) }}</span></div>
            <div class="info-item"><span class="muted">活跃峰值</span><span>{{ profile?.active_time ? profile.active_time.peak_hour + '时 / ' + weekdayLabel(profile.active_time.peak_weekday) : '-' }}</span></div>
            <div class="info-item"><span class="muted">消费力</span>
              <el-tag v-if="profile?.spending_power" :type="stageTagType(profile.spending_power) as any" size="small" effect="light">{{ profile.spending_power }}</el-tag>
              <span v-else>-</span>
            </div>
          </div>
          <div class="tag-row mt-12">
            <div class="muted" style="font-size: 12px">生命周期</div>
            <el-tag v-if="profile?.lifecycle_stage" :type="stageTagType(profile.lifecycle_stage) as any" size="small" effect="dark">{{ profile.lifecycle_stage }}</el-tag>
            <span v-else class="muted">-</span>
          </div>
          <div class="tag-row mt-12">
            <div class="muted" style="font-size: 12px">RFM 分群</div>
            <el-tag v-if="profile?.rfm" type="primary" size="small" effect="dark">{{ profile.rfm.segment }} · 评分 {{ profile.rfm.rfm_score }}</el-tag>
            <span v-else class="muted">-</span>
          </div>
        </ChartCard>
      </el-col>

      <!-- 预测 -->
      <el-col :xs="24" :lg="16">
        <ChartCard title="购买 / 流失预测" subtitle="基于观察窗口特征，时间切分防泄漏" height="auto">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12">
              <div class="pred-block">
                <div class="flex-between">
                  <span class="muted" style="font-size: 12.5px">未来 {{ profile?.predictions.purchase?.label_days ?? 7 }} 天购买概率</span>
                  <span class="pred-value" :class="{ 'is-high': (profile?.predictions.purchase?.purchase_probability ?? 0) >= 0.5 }">
                    {{ fmtProb(profile?.predictions.purchase?.purchase_probability) }}
                  </span>
                </div>
                <el-progress
                  :percentage="Math.round((profile?.predictions.purchase?.purchase_probability ?? 0) * 100)"
                  :color="(profile?.predictions.purchase?.purchase_probability ?? 0) >= 0.5 ? '#c0504d' : '#3457a8'"
                  :stroke-width="10"
                  :show-text="false"
                  class="mt-12"
                />
                <div class="muted mt-12" style="font-size: 11.5px">
                  模型：{{ modelLabel(profile?.predictions.purchase?.model) }} · 观察截止：{{ fmtDate(profile?.predictions.purchase?.obs_end) }}
                </div>
              </div>
            </el-col>
            <el-col :xs="24" :sm="12">
              <div class="pred-block">
                <div class="flex-between">
                  <span class="muted" style="font-size: 12.5px">未来 30 天流失概率</span>
                  <span class="pred-value" :class="{
                    'is-high': (profile?.predictions.churn?.churn_probability ?? 0) >= 0.5,
                  }">{{ fmtProb(profile?.predictions.churn?.churn_probability) }}</span>
                </div>
                <el-progress
                  :percentage="Math.round((profile?.predictions.churn?.churn_probability ?? 0) * 100)"
                  :color="(profile?.predictions.churn?.churn_probability ?? 0) >= 0.5 ? '#c0504d' : '#4a9d9c'"
                  :stroke-width="10"
                  :show-text="false"
                  class="mt-12"
                />
                <div class="flex-between mt-12">
                  <span class="muted" style="font-size: 11.5px">观察截止：{{ fmtDate(profile?.predictions.churn?.obs_end) }}</span>
                  <el-tag v-if="profile?.predictions.churn" :type="riskTagType(profile.predictions.churn.risk_level) as any" size="small" effect="dark">
                    风险：{{ riskLabel(profile.predictions.churn.risk_level) }}
                  </el-tag>
                </div>
              </div>
            </el-col>
          </el-row>
          <el-alert
            v-if="!profile?.predictions.purchase && !profile?.predictions.churn"
            type="info"
            :closable="false"
            title="该用户暂无预测记录（可能不在观察窗口活跃用户范围内）"
            class="mt-12"
          />
        </ChartCard>
      </el-col>
    </el-row>

    <!-- 偏好 -->
    <el-row :gutter="16" class="mt-16">
      <el-col :xs="24" :lg="12">
        <ChartCard title="偏好分类" height="260px">
          <EChart :option="prefCategoryOption" height="240px" />
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="12">
        <ChartCard title="偏好品牌" height="260px">
          <EChart :option="prefBrandOption" height="240px" />
        </ChartCard>
      </el-col>
    </el-row>

    <!-- 推荐结果 -->
    <ChartCard title="个性化推荐" subtitle="切换算法查看不同推荐与原因" class="mt-16" height="auto">
      <template #head>
        <div class="flex-center gap-12">
          <el-select v-model="algorithm" size="small" style="width: 170px">
            <el-option v-for="a in ALGORITHMS" :key="a" :label="ALGORITHM_LABELS[a]" :value="a" />
          </el-select>
          <el-input-number v-model="topK" :min="5" :max="20" :step="5" size="small" controls-position="right" style="width: 110px" />
        </div>
      </template>
      <div v-loading="recLoading">
        <el-alert v-if="hasRecError" type="warning" :closable="false" :title="recResult?.error || '推荐生成失败'" class="mb-12" />
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

    <!-- 行为 & 订单 -->
    <el-row :gutter="16" class="mt-16">
      <el-col :xs="24" :lg="12">
        <ChartCard title="最近行为记录" height="auto">
          <el-table :data="behaviors.slice(0, 12)" size="small" class="dense-table" stripe max-height="360">
            <el-table-column label="时间" width="140">
              <template #default="{ row }">{{ fmtDateTime(row.event_time) }}</template>
            </el-table-column>
            <el-table-column label="行为" width="80">
              <template #default="{ row }">
                <el-tag :type="(row.behavior_type === 'buy' ? 'danger' : row.behavior_type === 'cart' ? 'warning' : 'info') as any" size="small" effect="light">{{ behaviorLabel(row.behavior_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="item_id" label="商品 ID" min-width="120" show-overflow-tooltip />
            <el-table-column label="设备" width="90">
              <template #default="{ row }">{{ deviceLabel(row.device_type) }}</template>
            </el-table-column>
            <el-table-column label="渠道" width="100">
              <template #default="{ row }">{{ channelLabel(row.channel) }}</template>
            </el-table-column>
          </el-table>
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="12">
        <ChartCard title="订单记录" height="auto">
          <el-empty v-if="!orders.length" description="暂无订单" />
          <div v-else class="order-list">
            <div v-for="o in orders.slice(0, 8)" :key="o.order_id" class="order-item">
              <div class="flex-between">
                <span class="mono" style="font-size: 12.5px">{{ o.order_id }}</span>
                <el-tag size="small" effect="light" :type="(o.status === 'paid' ? 'success' : o.status === 'cancelled' ? 'info' : 'warning') as any">{{ orderStatusLabel(o.status) }}</el-tag>
              </div>
              <div class="flex-between mt-8">
                <span class="muted" style="font-size: 11.5px">{{ fmtDateTime(o.order_time) }} · {{ payMethodLabel(o.payment_method) }}</span>
                <span class="mono" style="font-weight: 600; color: var(--color-primary)">{{ fmtMoneyFull(o.total_amount) }}</span>
              </div>
              <div class="muted mt-8" style="font-size: 11.5px">
                <span v-for="(oi, idx) in o.order_items" :key="idx">{{ oi.item_name || oi.item_id }} ×{{ oi.quantity }}<span v-if="idx < o.order_items.length - 1"> · </span></span>
              </div>
            </div>
          </div>
        </ChartCard>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}
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
.tag-row {
  display: flex;
  align-items: center;
  gap: 10px;
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
.order-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
}
.order-item {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}
</style>
