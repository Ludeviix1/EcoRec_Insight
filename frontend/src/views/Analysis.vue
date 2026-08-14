<script setup lang="ts">
import { ref } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import RfmTab from '@/components/analysis/RfmTab.vue'
import LifecycleTab from '@/components/analysis/LifecycleTab.vue'
import CohortTab from '@/components/analysis/CohortTab.vue'
import PathTab from '@/components/analysis/PathTab.vue'
import ChannelTab from '@/components/analysis/ChannelTab.vue'
import DeviceTab from '@/components/analysis/DeviceTab.vue'
import PriceTab from '@/components/analysis/PriceTab.vue'
import AssociationTab from '@/components/analysis/AssociationTab.vue'
import SegmentsTab from '@/components/analysis/SegmentsTab.vue'
import FindingsTab from '@/components/analysis/FindingsTab.vue'

const activeTab = ref('rfm')
const activated = ref<Record<string, boolean>>({ rfm: true })

function onTabClick(name: string) {
  activated.value[name] = true
}
</script>

<template>
  <div>
    <PageHeader title="深度分析" desc="RFM 分群 · 生命周期 · 同期群留存 · 购买路径 · 渠道 / 设备 · 价格 · 关联规则 · 用户分群 · 业务发现" />

    <el-tabs v-model="activeTab" type="border-card" @tab-click="(pane: any) => onTabClick(pane.paneName)">
      <el-tab-pane label="RFM 分群" name="rfm"><RfmTab v-if="activated.rfm" /></el-tab-pane>
      <el-tab-pane label="生命周期" name="lifecycle"><LifecycleTab v-if="activated.lifecycle" /></el-tab-pane>
      <el-tab-pane label="同期群留存" name="cohort"><CohortTab v-if="activated.cohort" /></el-tab-pane>
      <el-tab-pane label="购买路径" name="path"><PathTab v-if="activated.path" /></el-tab-pane>
      <el-tab-pane label="渠道" name="channel"><ChannelTab v-if="activated.channel" /></el-tab-pane>
      <el-tab-pane label="设备" name="device"><DeviceTab v-if="activated.device" /></el-tab-pane>
      <el-tab-pane label="价格" name="price"><PriceTab v-if="activated.price" /></el-tab-pane>
      <el-tab-pane label="关联规则" name="association"><AssociationTab v-if="activated.association" /></el-tab-pane>
      <el-tab-pane label="用户分群" name="segments"><SegmentsTab v-if="activated.segments" /></el-tab-pane>
      <el-tab-pane label="业务发现" name="findings"><FindingsTab v-if="activated.findings" /></el-tab-pane>
    </el-tabs>
  </div>
</template>
