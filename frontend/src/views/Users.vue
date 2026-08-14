<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import { usersApi } from '@/api'
import { fmtDate, genderLabel } from '@/utils/format'
import type { UserRow } from '@/types'

const router = useRouter()
const loading = ref(false)
const items = ref<UserRow[]>([])
const total = ref(0)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)

async function load() {
  loading.value = true
  try {
    const res = await usersApi.list({
      keyword: keyword.value || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    items.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
}
function onPageChange(p: number) {
  page.value = p
  load()
}
function goDetail(row: UserRow) {
  router.push(`/users/${row.user_id}`)
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="用户管理" desc="浏览与检索用户，点击查看用户画像、预测与推荐">
      <el-input
        v-model="keyword"
        placeholder="搜索用户 ID 或城市"
        clearable
        style="width: 240px"
        @keyup.enter="onSearch"
        @clear="onSearch"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" @click="onSearch">搜索</el-button>
    </PageHeader>

    <div class="card card-pad">
      <el-table
        v-loading="loading"
        :data="items"
        size="default"
        stripe
        highlight-current-row
        @row-click="goDetail"
        style="cursor: pointer"
      >
        <el-table-column prop="user_id" label="用户 ID" width="130" />
        <el-table-column prop="gender" label="性别" width="80">
          <template #default="{ row }">{{ genderLabel(row.gender) }}</template>
        </el-table-column>
        <el-table-column prop="age" label="年龄" width="80" align="right" />
        <el-table-column prop="city" label="城市" width="120" />
        <el-table-column label="注册时间" width="130">
          <template #default="{ row }">{{ fmtDate(row.register_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click.stop="goDetail(row)">查看画像</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无用户数据" />
        </template>
      </el-table>

      <div class="flex-between mt-16">
        <span class="muted" style="font-size: 12.5px">共 {{ total }} 位用户</span>
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next, jumper"
          background
          @current-change="onPageChange"
        />
      </div>
    </div>
  </div>
</template>
