<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { usersApi } from '@/api'
import { genderLabel } from '@/utils/format'
import type { UserRow } from '@/types'

const props = defineProps<{
  modelValue?: string
  placeholder?: string
  size?: 'small' | 'default' | 'large'
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'select', user: UserRow): void
}>()

const options = ref<UserRow[]>([])
const loading = ref(false)
const inner = ref(props.modelValue ?? '')

watch(
  () => props.modelValue,
  (v) => {
    inner.value = v ?? ''
  },
)

async function search(keyword: string) {
  loading.value = true
  try {
    const page = await usersApi.list({ keyword: keyword || undefined, limit: 30, offset: 0 })
    options.value = page.items
  } finally {
    loading.value = false
  }
}

function onChange(val: string) {
  emit('update:modelValue', val)
  const u = options.value.find((o) => o.user_id === val)
  if (u) emit('select', u)
}

onMounted(() => search(''))
</script>

<template>
  <el-select
    v-model="inner"
    filterable
    remote
    clearable
    reserve-keyword
    :remote-method="search"
    :loading="loading"
    :placeholder="placeholder || '搜索用户 ID 或城市'"
    :size="size || 'default'"
    style="width: 100%"
    @change="onChange"
  >
    <el-option
      v-for="u in options"
      :key="u.user_id"
      :label="`${u.user_id} · ${genderLabel(u.gender)}/${u.age} · ${u.city}`"
      :value="u.user_id"
    />
  </el-select>
</template>
