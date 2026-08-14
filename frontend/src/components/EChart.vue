<script setup lang="ts">
import { ref, shallowRef, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { echarts, type EChartsOption } from '@/utils/echarts'

const props = withDefaults(
  defineProps<{
    option: EChartsOption
    height?: string
    loading?: boolean
  }>(),
  {
    height: '300px',
    loading: false,
  },
)

const el = ref<HTMLDivElement | null>(null)
const chart = shallowRef<echarts.ECharts | null>(null)
let observer: ResizeObserver | null = null

function render() {
  if (!el.value) return
  if (!chart.value) {
    chart.value = echarts.init(el.value)
    chart.value.setOption(props.option, true)
  } else {
    chart.value.setOption(props.option, true)
  }
}

watch(
  () => props.option,
  () => render(),
  { deep: true },
)

onMounted(async () => {
  await nextTick()
  render()
  observer = new ResizeObserver(() => {
    chart.value?.resize()
  })
  if (el.value) observer.observe(el.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart.value?.dispose()
  chart.value = null
})
</script>

<template>
  <div
    v-loading="loading"
    class="echart-wrap"
    :style="{ height }"
  >
    <div ref="el" class="echart-canvas"></div>
  </div>
</template>

<style scoped>
.echart-wrap {
  width: 100%;
}
.echart-canvas {
  width: 100%;
  height: 100%;
}
</style>
