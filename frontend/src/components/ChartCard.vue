<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    subtitle?: string
    height?: string
    loading?: boolean
  }>(),
  {
    height: '300px',
    loading: false,
  },
)
</script>

<template>
  <div class="card chart-card">
    <div v-if="title || $slots.head" class="chart-card__head">
      <div class="chart-card__title">
        <span v-if="title" class="section-title">{{ title }}</span>
        <span v-if="subtitle" class="muted" style="font-size: 12px; font-weight: 400; margin-left: 4px">{{ subtitle }}</span>
      </div>
      <div class="chart-card__extra"><slot name="head" /></div>
    </div>
    <div v-loading="loading" class="chart-card__body" :style="{ minHeight: height }">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.chart-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.chart-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 14px 18px 0;
  gap: 12px;
}
.chart-card__title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}
.chart-card__body {
  padding: 8px 14px 14px;
  flex: 1;
}
</style>
