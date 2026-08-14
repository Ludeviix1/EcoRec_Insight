<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { analysisApi } from '@/api'
import type { FindingsResponse } from '@/types'

const loading = ref(false)
const data = ref<FindingsResponse | null>(null)
const activeNames = ref<string[]>([])

async function load() {
  loading.value = true
  try {
    data.value = await analysisApi.findings()
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-alert
      v-if="data?.disclaimer"
      type="warning"
      :closable="false"
      :title="data.disclaimer"
      class="mb-16"
      show-icon
    />
    <div class="card card-pad">
      <el-collapse v-model="activeNames">
        <el-collapse-item
          v-for="domain in data?.domains ?? []"
          :key="domain.domain"
          :name="domain.domain"
        >
          <template #title>
            <div class="flex-center gap-8">
              <span style="font-weight: 600; font-size: 13.5px">{{ domain.title }}</span>
              <el-tag size="small" effect="plain" type="info">{{ domain.findings.length }} 项发现</el-tag>
            </div>
          </template>
          <div v-for="(f, i) in domain.findings" :key="i" class="finding">
            <div class="finding__metric">{{ i + 1 }}. {{ f['现象'] }}</div>
            <div class="finding__block">
              <span class="finding__label">证据</span>
              <ul class="finding__evidence">
                <li v-for="(e, j) in f['证据'] ?? []" :key="j">{{ e }}</li>
              </ul>
            </div>
            <div class="finding__block">
              <span class="finding__label">可能原因</span>
              <span>{{ f['可能原因'] }}</span>
            </div>
            <div class="finding__block">
              <span class="finding__label">业务建议</span>
              <span>{{ f['业务建议'] }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<style scoped>
.finding {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin-bottom: 10px;
  background: #fbfcfe;
}
.finding__metric {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
  color: var(--color-primary-dark);
}
.finding__block {
  display: flex;
  gap: 10px;
  font-size: 12.5px;
  line-height: 1.6;
  margin-bottom: 4px;
}
.finding__label {
  flex-shrink: 0;
  width: 64px;
  color: var(--color-text-secondary);
  font-weight: 600;
}
.finding__evidence {
  margin: 0;
  padding-left: 16px;
}
</style>
