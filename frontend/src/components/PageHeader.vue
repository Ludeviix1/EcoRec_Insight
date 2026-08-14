<script setup lang="ts">
defineProps<{
  title: string
  desc?: string
}>()
</script>

<template>
  <div class="page-header mb-16">
    <h2 class="page-title">{{ title }}</h2>
    <p v-if="desc" class="page-desc">{{ desc }}</p>
    <div v-if="$slots.default" class="page-header__actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 4px 16px;
}
.page-header__actions {
  margin-left: auto;
}
</style>
