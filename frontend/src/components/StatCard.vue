<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: string | number
    suffix?: string
    hint?: string
    icon?: string
    accent?: string
  }>(),
  {
    accent: '#3457a8',
  },
)

const iconStyle = computed(() => ({
  color: props.accent,
  background: props.accent + '14',
}))
</script>

<template>
  <div class="card stat-card card-pad">
    <div class="flex-between">
      <div class="grow">
        <div class="stat-card__label">{{ label }}</div>
        <div class="stat-card__value mono">
          {{ value }}<span v-if="suffix" class="stat-card__suffix">{{ suffix }}</span>
        </div>
        <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
      </div>
      <div v-if="icon" class="stat-card__icon" :style="iconStyle">
        <el-icon :size="22"><component :is="icon" /></el-icon>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  transition: box-shadow 0.18s, transform 0.18s;
}
.stat-card:hover {
  box-shadow: var(--shadow-hover);
  transform: translateY(-1px);
}
.stat-card__label {
  font-size: 12.5px;
  color: var(--color-text-secondary);
}
.stat-card__value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.25;
  margin-top: 6px;
  overflow-wrap: break-word;
  word-break: break-word;
}
.stat-card__suffix {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-left: 4px;
}
.stat-card__hint {
  font-size: 11.5px;
  color: var(--color-text-placeholder);
  margin-top: 4px;
}
.stat-card__icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
</style>
