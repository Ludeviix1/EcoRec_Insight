<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import EChart from '@/components/EChart.vue'
import ChartCard from '@/components/ChartCard.vue'
import StatCard from '@/components/StatCard.vue'
import PageHeader from '@/components/PageHeader.vue'
import { itemsApi, type ItemDetail } from '@/api'
import { BEHAVIOR_COLORS, baseTooltip, baseGrid, type EChartsOption } from '@/utils/echarts'
import { fmtInt, fmtMoney, fmtMoneyFull, fmtDate, fmtPct, fmtNum, behaviorLabel } from '@/utils/format'
import { stageTagType } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const itemId = computed(() => String(route.params.id))
const loading = ref(false)
const item = ref<ItemDetail | null>(null)

async function load() {
  loading.value = true
  try {
    item.value = await itemsApi.detail(itemId.value)
  } finally {
    loading.value = false
  }
}
onMounted(load)

const stat = computed(() => item.value?.statistics)
const behavior = computed(() => stat.value?.behavior)

const behaviorOption = computed<EChartsOption>(() => {
  const b = behavior.value
  const keys = ['pv', 'click', 'collect', 'cart', 'buy']
  return {
    tooltip: baseTooltip('item'),
    grid: { left: 40, right: 20, top: 16, bottom: 30, containLabel: true },
    xAxis: { type: 'category', data: keys.map((k) => behaviorLabel(k)), axisLine: { lineStyle: { color: '#d1d5db' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f0f2f6' } }, axisLabel: { color: '#9ca3af', fontSize: 11 } },
    series: [
      {
        type: 'bar',
        data: keys.map((k) => ({ value: (b as any)?.[k] ?? 0, itemStyle: { color: BEHAVIOR_COLORS[k], borderRadius: [3, 3, 0, 0] } })),
        barMaxWidth: 36,
      },
    ],
  }
})

const behaviorStats = computed(() => {
  const b = behavior.value
  return [
    { label: '浏览', value: fmtInt(b?.pv), accent: '#6ba3d0' },
    { label: '点击', value: fmtInt(b?.click), accent: '#4a9d9c' },
    { label: '收藏', value: fmtInt(b?.collect), accent: '#d98a2b' },
    { label: '加购', value: fmtInt(b?.cart), accent: '#8e6fc0' },
    { label: '购买', value: fmtInt(b?.buy), accent: '#c0504d' },
    { label: '触达用户', value: fmtInt(b?.unique_users), accent: '#3457a8' },
  ]
})
const salesStats = computed(() => {
  const s = stat.value?.sales
  return [
    { label: '销量', value: fmtInt(s?.sold), accent: '#c0504d' },
    { label: '订单数', value: fmtInt(s?.orders), accent: '#3457a8' },
    { label: '销售额', value: fmtMoney(s?.gmv), hint: fmtMoneyFull(s?.gmv), accent: '#2f9e6e' },
    { label: '转化率', value: fmtPct(behavior.value?.conversion_rate), accent: '#d98a2b' },
    { label: '热度分', value: fmtNum(stat.value?.heat_score, 2), accent: '#8e6fc0' },
  ]
})
</script>

<template>
  <div v-loading="loading">
    <PageHeader :title="item?.item_name || `商品 ${itemId}`" desc="商品画像 · 行为热度 · 销售统计">
      <el-button @click="router.push('/items')"><el-icon><ArrowLeft /></el-icon>返回列表</el-button>
    </PageHeader>

    <!-- 基础信息 -->
    <div class="card card-pad mb-16">
      <div class="info-grid">
        <div class="info-item"><span class="muted">商品 ID</span><span class="mono">{{ item?.item_id }}</span></div>
        <div class="info-item"><span class="muted">分类</span><span>{{ item?.category_name || item?.category_id }}</span></div>
        <div class="info-item"><span class="muted">品牌</span><span>{{ item?.brand || '-' }}</span></div>
        <div class="info-item"><span class="muted">价格</span><span class="mono" style="color: var(--color-primary); font-weight: 600">{{ fmtMoneyFull(item?.price) }}</span></div>
        <div class="info-item"><span class="muted">库存</span><span class="mono">{{ fmtInt(item?.stock) }}</span></div>
        <div class="info-item"><span class="muted">状态</span>
          <el-tag :type="(item?.status === 1 ? 'success' : 'info') as any" size="small" effect="light">{{ item?.status === 1 ? '上架' : '下架' }}</el-tag>
        </div>
        <div class="info-item"><span class="muted">创建时间</span><span>{{ fmtDate(item?.created_at) }}</span></div>
        <div class="info-item"><span class="muted">价格档</span>
          <el-tag v-if="stat?.price_band" size="small" effect="light" type="info">{{ stat.price_band }}</el-tag>
          <span v-else>-</span>
        </div>
        <div class="info-item"><span class="muted">商品生命周期</span>
          <el-tag v-if="stat?.lifecycle_stage" :type="stageTagType(stat.lifecycle_stage) as any" size="small" effect="dark">{{ stat.lifecycle_stage }}</el-tag>
          <span v-else>-</span>
        </div>
      </div>
    </div>

    <!-- 行为 KPI -->
    <div class="stat-row mb-16">
      <StatCard v-for="s in behaviorStats" :key="s.label" :label="s.label" :value="s.value" :accent="s.accent" />
    </div>
    <div class="stat-row mb-16">
      <StatCard v-for="s in salesStats" :key="s.label" :label="s.label" :value="s.value" :hint="s.hint" :accent="s.accent" />
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="12">
        <ChartCard title="行为分布" subtitle="浏览 → 点击 → 收藏 → 加购 → 购买" height="300px">
          <EChart :option="behaviorOption" height="280px" />
        </ChartCard>
      </el-col>
      <el-col :xs="24" :lg="12">
        <ChartCard title="销售概览" height="300px">
          <div class="sales-summary">
            <div class="sales-row">
              <span class="muted">累计销量</span>
              <span class="metric-value mono">{{ fmtInt(stat?.sales?.sold) }}</span>
            </div>
            <div class="sales-row">
              <span class="muted">累计订单</span>
              <span class="metric-value mono">{{ fmtInt(stat?.sales?.orders) }}</span>
            </div>
            <div class="sales-row">
              <span class="muted">累计销售额</span>
              <span class="metric-value mono" style="color: var(--color-success)">{{ fmtMoneyFull(stat?.sales?.gmv) }}</span>
            </div>
            <div class="sales-row">
              <span class="muted">热度评分</span>
              <span class="metric-value mono" style="color: var(--color-primary)">{{ fmtNum(stat?.heat_score, 2) }}</span>
            </div>
            <el-divider />
            <div class="muted" style="font-size: 12px; line-height: 1.6">
              转化率 = 购买用户 / 触达用户。热度分综合浏览 / 交互 / 购买等行为加权得出。
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
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px 20px;
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
.sales-summary {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 8px 4px;
}
.sales-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
